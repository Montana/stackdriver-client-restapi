import httpRequests 

from . import __version__

from .restapi import RestApi

import logging
logger = logging.getLogger(__name__)


class AnonStackInterface(object):
    def __init__(self, rest_class, client, endpoint_prefix=''):

        self._rest_class = self._mapToRestClass(rest_class)
        self._rest_client = client

        # endpoint is always lowercase
        self._endpoint = '%s%s/' % (endpoint_prefix, self._mapToRestClass(rest_class).lower())

    def __call__(self, data=None):
        """ If called with data create an AnonStackObject """

        if data is None:
            data = {}

        if 'resource' in data:
            self._isrestclass(data['resource'], self._rest_class)

        return AnonStackObject(self._rest_class, self._rest_client, data)

    def __repr__(self):
        return '%s StackInterface (%s%s)' % (self._rest_class, self._rest_client.entrypoint, self._endpoint)

    def _mapToRestClass(self, rest_class):
      
        if '_' in rest_class or sum(rc.isupper() for rc in rest_class) == 1:
            return rest_class
        underscore_str = rest_class[0]
        for rc in rest_class[1:]:
            if rc.isupper():
                underscore_str += '_'
            underscore_str += rc
        return underscore_str

    def _wrap_rest_data_one(self, item):
        if 'resource' not in item:
            logger.warn('Trying to wrap an object without a resource, returning the raw dict instead.')
            return item

        cls = self._parse_class_from_resource(item['resource'])
        return AnonStackObject(cls, self._rest_client, item)

    def _wrap_rest_data(self, data):
  
        if isinstance(data, dict):
            return self._wrap_rest_data_one(data)

        if not isinstance(data, list):
            raise RuntimeError("Result data must be a dict or a list: '%s' was returned" % type(data))

        objs = []
        for item in data:
            objs.append(self._wrap_rest_data_one(item))
        return objs

    def _parse_class_from_resource(self, resource):

        parts = resource.split('/')
        if not parts[-1].rstrip():
            del parts[-1]

        cls = parts[-2]
        cls = cls[0].upper() + cls[1:].lower()
        return cls

    def _isrestclass(self, resource, cls):
        return self._parse_class_from_resource(resource) == cls

    def _unwind_result(self, result):
      
        if 'data' not in result:
            logger.error('Result does not contain a data field')
            raise ValueError('Result does not contain a data field')

        return result['data']
    
    # fetch endpoints
    def _versioned_endpoint(self, endpoint, id=None, action=None):
        uri = 'v%s/%s' % (self._rest_client.api_version, endpoint)
        if id is not None:
            uri = '%s%s/' % (uri, id)
        if action is not None:
            uri = '%s%s/' % (uri, action)

        return uri

    def __getattr__(self, attr):
      
        if attr[0].isupper():
            # create an interface with the attr as the class for the endpoint
            return AnonStackInterface(attr, self._rest_client, self._endpoint)
        else:
            raise AttributeError

    def GET(self, id=None, params=None, action=None, headers=None):
    
        endpoint = None
        endpoint = self._versioned_endpoint(self._endpoint, id, action)

        rest_result = self._rest_client.get(endpoint, params=params, headers=headers)

        return self._wrap_rest_data(self._unwind_result(rest_result))

    def POST(self, data=None, headers=None, action=None):
  
        endpoint = self._versioned_endpoint(self._endpoint, action=action)

        resp = self._rest_client.post(endpoint, data=data, headers=headers)

        result = self._unwind_result(resp)

        return result

    def LIST(self, params=None, headers=None):
        return self.GET(params=params, headers=headers)


class AnonStackObject(AnonStackInterface, dict):
    def __init__(self, rest_class, client, data):
       
        if not isinstance(data, dict):
            raise TypeError('Object must be a dictionary')

        # copy all items in dict
        for key, value in data.iteritems():
            self[key] = value

        super(AnonStackObject, self).__init__(rest_class, client)

    def __getattr__(self, attr):
        if not attr in self:
            raise AttributeError

        return self[attr]

    def __setattr__(self, attr, value):
        if not attr.startswith('_'):
            self[attr] = value

        super(AnonStackObject, self).__setattr__(attr, value)

    def __repr__(self):
        return '%s(%s)' % (self._rest_class, dict.__repr__(self))

    def CREATE(self, headers=None):
      
        resource = self.get('resource', None)
        if resource:
            raise ValueError('Can not create, this resource already exists.')

        endpoint = self._versioned_endpoint(self._endpoint)
        resp = self._rest_client.post(endpoint, data=self, headers=headers)

        data = self._unwind_result(resp)

   
        for key, value in data.iteritems():
            self[key] = value

        return self

    def UPDATE(self, headers=None):
       
        resource = self.get('resource', None)
        if not resource:
            raise ValueError('Must have a resource to update.')

        resp = self._rest_client.put(resource, data=self, headers=headers)

        data = self._unwind_result(resp)

        # merge response in
        for key, value in data.iteritems():
            self[key] = value

        return self

    def _get_endpoint(self, action=None):
        endpoint = self.get('resource')
        if not endpoint:
            id = self.get('id')
            endpoint = self._versioned_endpoint(self._endpoint, id)

        if action is not None:
            endpoint = '%s%s/' % (endpoint, action)

        return endpoint

    def PUT(self, data=None, action=None, headers=None):
        endpoint = self._get_endpoint(action)
        resp = self._rest_client.put(endpoint, data=data, headers=headers)

        print resp
        result = self._unwind_result(resp)

        return result

    def GET(self, params=None, action=None, headers=None):
        endpoint = self._get_endpoint(action)
        resp = self._rest_client.get(endpoint, params=params, headers=headers)

        result = self._unwind_result(resp)

        return result

    def DELETE(self, headers=None):
       
        resource = self.get('resource')
        if resource is None:
            raise ValueError('Can not delete, this is not a resource from the server.')

        resp = self._rest_client.delete(resource, headers=headers)

        data = self._unwind_result(resp)

        # merge response in
        for key, value in data.iteritems():
            self[key] = value

        return self


class StackApi(object):
    API_VERSION = '0.2'

    def __init__(self, entrypoint_uri='https://api.stackdriver.com/', version=API_VERSION, apikey=None, use_custom_headers=False, transport_controller=None, transport_userdata=None):

        if not apikey and not use_custom_headers and not transport_controller:
            raise KeyError('apikey must be specified when talking to the Stackdriver API')
            
        self._rest_client = RestApi(entrypoint_uri,
                                    version,
                                    apikey,
                                    useragent='Stackdriver Python Client %s' % __version__,
                                    transport_controller=transport_controller,
                                    transport_userdata=transport_userdata)

    def __getattr__(self, attr):
       
        For any attr that starts with a capital letter create a AnonStackInterface

        __getattr__ will only trigger if the attr is not defined on the class
        
        if attr[0].isupper():
           
        else:
            raise AttributeError

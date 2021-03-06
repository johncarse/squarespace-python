import logging
from time import strftime, gmtime

import requests


__VERSION__ = '0.0.3'
api_baseurl = 'https://api.squarespace.com'
api_version = '0.1'


class SquarespaceError(Exception):
    pass


class Squarespace(object):
    """Represents orders from a particular squarespace store.

    :api_key:
        Your Squarespace API key. Required.

    :api_baseurl:
        The baseuri for the Squarespace API. You shouldn't need to change
        this.

    :api_version:
        The version of the Squarespace API to target. If you change this
        without making any code changes you may break this library.
    """
    def __init__(self, api_key, api_baseurl=api_baseurl, api_version=api_version, tracking_baseurl='https://tools.usps.com/go/TrackConfirmAction?tLabels='):
        self.api_key = api_key
        self.api_baseurl = api_baseurl
        self.api_version = api_version
        self.tracking_baseurl = tracking_baseurl

        # Setup our HTTP session
        self.http = requests.Session()
        self.http.headers.update({'Authorization': 'Bearer ' + self.api_key})
        self.useragent = 'Squarespace python API v%s by Zach White.' % __VERSION__
        self._next_page = None
        self.max_pages = 20  # How many pages worth of orders to fetch.
                             # If you need to fetch more than 100 orders you'll
                             # have to increase this

    @property
    def useragent(self):
        """Get the current useragent.
        """
        return self._useragent

    @useragent.setter
    def useragent(self, agent_string):
        """Set the User-Agent that will be used.
        """
        self._useragent = agent_string
        self.http.headers.update({'User-Agent': self._useragent})

    def post(self, path, object):
        """Post an `object` to the Squarespace API.

        :object:
            A dictionary containing JSON compatible key/value combinations.
        """
        url = '%s/%s/%s' % (self.api_baseurl, self.api_version, path)
        logging.debug('url:%s object:%s', url, object)
        return self.process_request(self.http.post(url, json=object))

    def get(self, path, args=None):
        """Retrieve an endpoint from the Squarespace API.
        """
        if not args:
            args = {}

        url = '%s/%s/%s' % (self.api_baseurl, self.api_version, path)
        logging.debug('url:%s args:%s', url, args)
        return self.process_request(self.http.get(url, params=args))

    def process_request(self, request):
        """Process a request and return the data.
        """
        if request.status_code in [200, 201]:
            return request.json()
        elif request.status_code == 204:
            return True
        elif request.status_code == 401:
            raise ValueError('The API key %s is not valid.', self.api_key)
        elif 200 < request.status_code < 299:
            logging.warning('Squarespace success response %s:', request.status_code)
            logging.warning(request.text)
            raise NotImplementedError("Squarespace sent us a success response we're not prepared for!")

        logging.error('Squarespace error response %s:', request.status_code)
        logging.error('URL: %s', request.url)
        logging.error(request.text)

        if 400 <= request.status_code < 499:
            raise RuntimeError("Squarespace thinks this request is bogus")
        if 500 <= request.status_code < 599:
            raise RuntimeError("Squarespace is having problems, try later.")

        raise RuntimeError("An unknown error occurred fetching your request.")

    def order(self, order_id=None, order_number=None):
        """Retrieve a single order.
        """
        if order_id:
            return self.get('commerce/orders/' + order_id)
        elif order_number:
            for order in self.all_orders():
                if order['orderNumber'] == order_number:
                    return order
        else:
            raise SquarespaceError('You must specify one of `order_id` or `order_number`')

    def orders(self, **args):
        """Retrieve the 20 latest orders, by modification date.
        """
        uri = 'commerce/orders'

        result = self.get(uri, args)
        self._next_page = result['pagination']['nextPageCursor'] if 'nextPageCursor' in result['pagination'] else None

        return result['result']

    def next_page(self):
        """Retrieve the next 20 orders, or None if there are no more orders.
        """
        return self.orders(cursor=self._next_page) if self._next_page else None

    def all_orders(self):
        orders = self.orders()

        count = 0
        while self._next_page:
            count += 1
            orders.extend(self.next_page())
            if count >= self.max_pages:
                logging.warning('%s.all_orders: max_pages (%s) hit.', self.__class__.__name__, self.max_pages)
                break

        return orders

    def fulfill(self, order_id, tracking_number, carrier_name, service_name, tracking_baseurl=None):
        """Mark an order as shipped.

        :param tracking_number:
            The shipping carrier's tracking number.
        :param carrier_name:
            The name of the shipping carrier, EG 'USPS'.
        :param service_name:
            The shipping service used, EG "First Class Package"
        """
        if not tracking_baseurl:
            tracking_baseurl = self.tracking_baseurl

        uri = 'commerce/orders/%s/fulfillments' % order_id
        fulfillment = {
            "shouldSendNotification": True,
            "shipments": [
                {
                    'shipDate': strftime('%Y-%m-%dT%H:%M:%SZ', gmtime()),
                    "carrierName": carrier_name,
                    "service": service_name,
                    "trackingNumber": tracking_number,
                    "trackingUrl": tracking_baseurl + tracking_number
                }
            ]
        }

        return self.post(uri, fulfillment)

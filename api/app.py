import json
import sys
import boto3
import botocore
from os import environ
import logging
import uuid
import time
from datetime import datetime, timedelta
from decimal import Decimal
'''
DecimalEncoder:
The following routines added to ensure that JSON-ified outputs don't have raw floats

'''
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return json.JSONEncoder.default(self, obj)

def parse_float(value):
    return Decimal(str(value))
'''
Set up our environment
'''
my_config = botocore.config.Config(region_name='us-east-1')
db = boto3.resource('dynamodb', config=my_config)

tablename = None
table = None
if __name__ != '__main__':
    tablename = environ['TABLE_NAME']
    table = db.Table(tablename)
    logging.basicConfig(level=logging.INFO)
else:
    tablename = 'notes_table_dummy'
    logging.basicConfig(level=logging.DEBUG)

if tablename == None:
    raise Exception("Cannot find environment variable TABLE_NAME")

logger = logging.getLogger('sls_notes_backend_handlers')


'''
Add CORS global enablement to headers

'''

def getResponseHeaders():
    d = {'Access-Control-Allow-Orgin' : '*'} #enable CORS from everywhere
    return d



'''
Slurp user_id from headers

'''
def getUserId(headers):
    if 'app_user_id' in headers:
        return headers['app_user_id']
    return None



'''
Slurp user_name from headers

'''
def getUserName(headers):
    if 'app_user_name' in headers:
        return headers['app_user_name']
    return None


'''
Route: POST /note

'''
def add_note_handler(event, context):
    mylambdafunction='add_note'

    try:
        # parse body from event
        body = None
        if 'body' in event:
            body = json.loads(event['body'])
        else:
            item = None
            eventkeys = ""
            for key in body.keys():
                eventkeys = eventkeys + " " + key
            return {
                'statusCode': 400,
                'error': f"{mylambdafunction}() - Cannot find 'body' in event",
                'event': event
            }
        # parse item from body
        if 'Item' in body:
            item = body['Item']
        else:
            bodykeys = ""
            for key in body.keys():
                bodykeys = bodykeys + " " + key
            return {
                'statusCode': 400,
                'error': f"{mylambdafunction}() - Cannot find 'Item' in body",
                'bodykeys': bodykeys,
                'body': json.dumps(body, cls=DecimalEncoder)
            }

        # parse user information from headers
        item['user_id'] = getUserId(event['headers'])
        if item['user_id'] is None:
            return {
                'statusCode': 400,
                'error': "Cannot find 'app_user_id'  in headers",
                'data': json.dumps(event, cls=DecimalEncoder)
            }

        item['user_name'] = getUserName(event['headers'])
        if item['user_name'] is None:
            return {
                'statusCode': 400,
                'error': "Cannot find 'app_user_name' in 'headers'",
                'headers': json.dumps(headers, cls=DecimalEncoder)
            }

        # auto-generate a note id from the user name and a GUID
        item['note_id'] = item['user_id'] + ':' + str(uuid.uuid4())
        dt = datetime.now()
        # in production, we wouldn't expire peoples notes
        expires = dt + timedelta(days=180)
        # these are in 'unixtime', but the mktime returns a float so we turn it to a decimal
        item['timestamp'] = parse_float(time.mktime(dt.timetuple()))
        item['expires'] = parse_float(time.mktime(expires.timetuple()))
        if table != None:
            table.put_item(
                TableName=tablename,
                Item=item
            )
            response = {
                'statusCode': 200,
                'body': json.dumps(item, cls=DecimalEncoder)
            }
            return response
        else:
            # Called from the command line
            logger.debug(f"{mylambdafunction} Not updating table - TEST mode")
            response = {
                'statusCode': 200,
                'body': json.dumps(event, cls=DecimalEncoder)
            }
            return response


    # bad things happened, let's see if we can handle it ourselves
    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Code'] == 'InternalError': # Generic error
            # We grab the message, request ID, and HTTP code to give to customer support
            logger.critical(mylambdafunction + ' Error Message: {}'.format(err.response['Error']['Message']))
            logger.critical(mylambdafunction + ' Request ID: {}'.format(err.response['ResponseMetadata']['RequestId']))
            logger.critical(mylambdafunction + ' Http code: {}'.format(err.response['ResponseMetadata']['HTTPStatusCode']))
            raise err
        else:
            errbody= {
                'lambdafunction' : mylambdafunction,
                'code' : err.response['Error']['Code'],
                'message' : err.response['Error']['Message']
            }
            errorresponse = {
                'statusCode': err.response['ResponseMetadata']['HTTPStatusCode'],
                'body': 
                json.dumps( errbody )
            }
            return errorresponse
'''
Route: DELETE /note/t/{timestamp}

Use user_id/timestamp to find and delete a particular note.
user_id is in headers, and timestamp is part of the event.pathParameters
'''
def delete_note_handler(event, context):
    mylambdafunction='delete_note'
    try:
        timestamp = None
        # parse the timestamp from the event.pathParameters
        if 'pathParameters' in event:
            timestamp = event['pathParameters']['timestamp']
        else:
            # bad json sent in headers
            errbody= {
                'error' : f"{mylambdafunction}() - Cant find 'timestamp' in 'pathParameters'"
            }
            errorresponse = {
                'statusCode': 400,
                'error': json.dumps( errbody ),
                'data': json.dumps(event, cls=DecimalEncoder)
            }
            return errorresponse

        # parse the user_id from the headers
        user_id = getUserId(event['headers'])
        if user_id is None:
            return {
                'statusCode': 400,
                'error': "Cannot find 'app_user_id' in 'headers'",
                'data': json.dumps(event, cls=DecimalEncoder)
            }

        params = {
            'Key':{
                'user_id': user_id,
                'timestamp': int(timestamp)
            }
        }
        if table:
            table.delete_item(**params)
        else:
            logger.info(f"Running {mylambdafunction}() in testmode")
        response = {
            'statusCode': 200
        }
        return response



    # something bad happened
    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Code'] == 'InternalError': # Generic error
            # We grab the message, request ID, and HTTP code to give to customer support
            logger.critical(mylambdafunction + ' Error Message: {}'.format(err.response['Error']['Message']))
            logger.critical(mylambdafunction + ' Request ID: {}'.format(err.response['ResponseMetadata']['RequestId']))
            logger.critical(mylambdafunction + ' Http code: {}'.format(err.response['ResponseMetadata']['HTTPStatusCode']))
            raise err
        else:
            errbody= {
                'lambdafunction' : mylambdafunction,
                'code' : err.response['Error']['Code'],
                'message' : err.response['Error']['Message']
            }
            if  err.response['Error']['Message'] == 'The provided key element does not match the schema':
                errbody['params'] = params
            errorresponse = {
                'statusCode': err.response['ResponseMetadata']['HTTPStatusCode'],
                'body': 
                json.dumps( errbody )
            }
            return errorresponse
        
'''
Route: GET /note/n/{note_id}

Get the contents of a note from the note_id held in the pathParameter
'''


def get_note_handler(event, context):
    mylambdafunction='get_note'
    try:
        # parse note_id from the event.pathParamter
        note_id = None
        if 'pathParameters' in event and 'note_id' in event['pathParameters']:
            note_id = event['pathParameters']['note_id']
        else:
            return {
                'statusCode': 404,
                'headers': json.dumps(getResponseHeaders()),
                'error': 'No note_id in pathParameters'
            }

        # query parameters are to find a note where the note_id field matches
        params = {
            'TableName': tablename,
            'IndexName': 'note_id-index',
            'KeyConditionExpression': 'note_id = :note_id',
            'ExpressionAttributeValues': {
                ':note_id': note_id
            },
            'Limit': 1
        }
        if table is None:
            # running from command line, just dump the params
            return json.dumps(params)


        data = table.query(**params)
        if data and 'Items' in data:
            return {
                'statusCode': 200,
                'headers': json.dumps(getResponseHeaders()),
                'body': json.dumps(data['Items'][0],  cls=DecimalEncoder)
            }
        else:
            # no such note, return 204 - No Content
            return {
                'statusCode': 204,
                'headers': json.dumps(getResponseHeaders())
            }


    # bad things happened
    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Code'] == 'InternalError': # Generic error
            # We grab the message, request ID, and HTTP code to give to customer support
            logger.critical(mylambdafunction + ' Error Message: {}'.format(err.response['Error']['Message']))
            logger.critical(mylambdafunction + ' Request ID: {}'.format(err.response['ResponseMetadata']['RequestId']))
            logger.critical(mylambdafunction + ' Http code: {}'.format(err.response['ResponseMetadata']['HTTPStatusCode']))
            raise err
        else:
            errbody= {
                'lambdafunction' : mylambdafunction,
                'code' : err.response['Error']['Code'],
                'message' : err.response['Error']['Message']
            }
            errorresponse = {
                'statusCode': err.response['ResponseMetadata']['HTTPStatusCode'],
                'headers': json.dumps(getResponseHeaders()),
                'body': 
                json.dumps( errbody )
            }
            return errorresponse


'''
Route: GET /notes

Get multiple notes from the user (max count=5, default), user_id is in the headers
'''
def get_notes_handler(event, context):
    mylambdafunction='get_notes'
    try:
        # parse limit from queryStringParameters
        query = event['queryStringParameters']
        limit = query['limit'] if query and 'limit' in query else 5
        # parse user_id from headers
        user_id = getUserId(event['headers'])
        if user_id is None:
            return {
                'statusCode': 404,
                'headers': json.dumps(getResponseHeaders()),
                'error': "Cannot find 'app_user_id' in 'headers'",
                'data': json.dumps(event, cls=DecimalEncoder)
            }

        # query to get all notes (up to limit) matching field user_id
        params = {
            'TableName': tablename,
            'KeyConditionExpression': 'user_id = :uid',
            'ExpressionAttributeValues': {
                ':uid':  user_id
            },
            'Limit': limit,
            'ScanIndexForward': False

        }

        # possibly get start time to set up an exclusive start key
        startTimeStamp = int(query['start']) if query and 'start' in query else 0
        if(startTimeStamp > 0):
            params['exclusiveStartKey'] = {
                'user_id': user_id,
                'timestamp': startTimeStamp

            }
        
        data = None
        if table:
            data = table.query(**params)
        else:
            # running from the command line
            data = params
            logger.info("Running "+mylambdafunction+"() in testmode")
        
        response = {
            'statusCode': 200,
            'headers': json.dumps(getResponseHeaders()),
            'body': json.dumps(data,cls=DecimalEncoder)
        }
        return response


    # handle bad stuff
    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Code'] == 'InternalError': # Generic error
            # We grab the message, request ID, and HTTP code to give to customer support
            logger.critical(mylambdafunction + ' Error Message: {}'.format(err.response['Error']['Message']))
            logger.critical(mylambdafunction + ' Request ID: {}'.format(err.response['ResponseMetadata']['RequestId']))
            logger.critical(mylambdafunction + ' Http code: {}'.format(err.response['ResponseMetadata']['HTTPStatusCode']))
            raise err
        else:
            errbody= {
                'lambdafunction' : mylambdafunction,
                'code' : err.response['Error']['Code'],
                'message' : err.response['Error']['Message']
            }
            errorresponse = {
                'statusCode': err.response['ResponseMetadata']['HTTPStatusCode'],
                'headers': json.dumps(getResponseHeaders()),
                'body': json.dumps( errbody )
            }
            return errorresponse

'''
Route: PATCH /note

'''

def update_note_handler(event, context):
    mylambdafunction='update_notes'
    try:
        # try and parse body from event
        body = None
        if 'body' in event:
            body = json.loads(event['body'])
        else:
            item = None
            eventkeys = ""
            # try to build up a debug string of the top level keys in the map to figure out where we messed up
            for key in body.keys():
                eventkeys = eventkeys + " " + key
            return {
                'statusCode': 400,
                'headers': json.dumps(getResponseHeaders()),
                'error': f"{mylambdafunction}() - Cannot find 'body' in event",
                'event': event
            }
        # parse item from body
        if 'Item' in body:
            item = body['Item']
        else:
            bodykeys = ""
            for key in body.keys():
                bodykeys = bodykeys + " " + key
            return {
                'statusCode': 400,
                'error': f"{mylambdafunction}() - Cannot find 'Item' in body",
                'bodykeys': bodykeys,
                'headers': json.dumps(getResponseHeaders()),
                'body': json.dumps(body, cls=DecimalEncoder)
            }

        # parse user information from headers
        item['user_id'] = getUserId(event['headers'])
        if item['user_id'] is None:
            return {
                'statusCode': 400,
                'error': "Cannot find 'app_user_id'  in headers",
                'headers': json.dumps(getResponseHeaders()),
                'data': json.dumps(event, cls=DecimalEncoder)
            }
        item['user_name'] = getUserName(event['headers'])
        if item['user_name'] is None:
            return {
                'statusCode': 400,
                'error': "Cannot find 'app_user_name' in 'headers'",
                'headers': json.dumps(headers, cls=DecimalEncoder)
            }
        # parse timestamp from item
        if item['timestamp'] is None:
            return {
                'statusCode': 400,
                'error': "Cannot find 'timestamp' in 'Item'",
                'headers': json.dumps(item, cls=DecimalEncoder)
            }
        timestamp = item['timestamp']
        if item['note_id'] is None:
            return {
                'statusCode': 400,
                'error': "Cannot find 'note_id' in 'Item'",
                'headers': json.dumps(item, cls=DecimalEncoder)
            }
        # we are going to update the note, but not modify the time stamp because it is a key element
        # however, we will update the expiration date.
        # note that for production, there should be no expiration times
        expires = datetime.now() + timedelta(days=180)
        unix_expires = parse_float(time.mktime(expires.timetuple()))
        item['expires'] = unix_expires
        data = None
        params = {
            'TableName': tablename,
            'Item': item,
            'ConditionExpression': '#t = :t',
            'ExpressionAttributeNames': {
                '#t': 'timestamp'
            },
            'ExpressionAttributeValues': {
                ':t': timestamp
            }
        }
        if table:
            data = table.put_item(**params)
        else:
            # called from the command line
            logger.debug('Not updating table - TEST mode')
        
        response = {
            'statusCode': 200,
            'headers': json.dumps(getResponseHeaders()),
            'body': json.dumps(item, cls=DecimalEncoder)
        }
        return response


    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Code'] == 'InternalError': # Generic error
            # We grab the message, request ID, and HTTP code to give to customer support
            logger.critical(mylambdafunction + ' Error Message: {}'.format(err.response['Error']['Message']))
            logger.critical(mylambdafunction + ' Request ID: {}'.format(err.response['ResponseMetadata']['RequestId']))
            logger.critical(mylambdafunction + ' Http code: {}'.format(err.response['ResponseMetadata']['HTTPStatusCode']))
            raise err
        else:
            errbody= {
                'lambdafunction' : mylambdafunction,
                'code' : err.response['Error']['Code'],
                'message' : err.response['Error']['Message']
            }
            errorresponse = {
                'statusCode': err.response['ResponseMetadata']['HTTPStatusCode'],
                'headers': json.dumps(getResponseHeaders()),
                'body': json.dumps( errbody )
            }
            if err.response['Error']['Code'] == 'ConditionalCheckFailedException':
                errorresponse['debug'] = f"No matching notes with timestamp='{timestamp}'"

            return errorresponse
##########################################################################################
if __name__ == '__main__':
    c = {"foo":"bar"}
    e = {
        "body": {
            "Item": {
                "title": "My First Note",
                "content": "Content of my first note",
                "cat": "general",
                "note_id": "robert.fairchild@yahoo.com:eebf7dfc-4cbd-45e0-9344-71f3e7a65e39",
                "timestamp": 1723331552
            }
        },
        "queryStringParameters": {
            "limit": 5
        },
        "pathParameters": {
            "note_id": "robert.fairchild@yahoo.com:eebf7dfc-4cbd-45e0-9344-71f3e7a65e39",
            "timestamp": 1723331552
        },
        "headers": {
            "app_user_id": "robert.fairchild@yahoo.com",
            "app_user_name": "Rob Fairchild"
        }
    } 
    print ("\n\nadd_note_handler() Returning:\n" + json.dumps(add_note_handler(e,c), indent=4))
#    print ("\n\ndelete_note_handler() Returning:\n" + json.dumps(delete_note_handler(e,c), indent=4))
#    print ("\n\nget_note_handler() Returning:\n" + json.dumps(get_note_handler(e,c), indent=4))
#    print ("\n\nget_notes_handler() Returning:\n" + json.dumps(get_notes_handler(e,c), indent=4))
#    print ("\n\nupdate_note_handler() Returning:\n" + json.dumps(update_note_handler(e,c), indent=4, cls=DecimalEncoder))
    


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

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return json.JSONEncoder.default(self, obj)

def parse_float(value):
    return Decimal(str(value))
# Set up our environment
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

# Set up our logger

logger = logging.getLogger('sls_notes_backend_handlers')


def getResponseHeaders():
    d = {'Access-Control-Allow-Orgin' : '*'} #enable CORS from everywhere
    return d

def getUserId(headers):
    if 'app_user_id' in headers:
        return headers['app_user_id']
    return None

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
        item['note_id'] = item['user_id'] + ':' + str(uuid.uuid4())
        dt = datetime.now()
        expires = dt + timedelta(days=180)
        # these are in 'unixtime'
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
            logger.debug(f"{mylambdafunction} Not updating table - TEST mode")
            response = {
                'statusCode': 200,
                'body': json.dumps(event, cls=DecimalEncoder)
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
                'body': 
                json.dumps( errbody )
            }
            return errorresponse
'''
Route: DELETE /note/t/{timestamp}

'''
def delete_note_handler(event, context):
    mylambdafunction='delete_note'
    try:
        timestamp = None
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

'''


def get_note_handler(event, context):
    mylambdafunction='get_note'
    try:
        note_id = None
        if 'pathParameters' in event and 'note_id' in event['pathParameters']:
            note_id = event['pathParameters']['note_id']
        else:
            return {
                'statusCode': 404,
                'headers': json.dumps(getResponseHeaders()),
                'error': 'No note_id in pathParameters'
            }

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
            return json.dumps(params)


        data = table.query(**params)
        if data and 'Items' in data:
#            print(json.dumps(data))
            return {
                'statusCode': 200,
                'headers': json.dumps(getResponseHeaders()),
                'body': json.dumps(data['Items'][0],  cls=DecimalEncoder)
                #'body': json.dumps(data['Item'][0], cls=DecimalEncoder)
                #'body': json.dumps(data['Item'][0])
        #        'body': "Hello World"
            }
        else:
            return {
                'statusCode': 404,
                'headers': json.dumps(getResponseHeaders()),
                'data': json.dumps(data, cls=DecimalEncoder)
            }


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

'''
def get_notes_handler(event, context):
    mylambdafunction='get_notes'
    try:
        query = event['queryStringParameters']
        limit = query['limit'] if query and 'limit' in query else 5
        user_id = getUserId(event['headers'])
        if user_id is None:
            return {
                'statusCode': 404,
                'headers': json.dumps(getResponseHeaders()),
                'error': "Cannot find 'app_user_id' in 'headers'",
                'data': json.dumps(event, cls=DecimalEncoder)
            }
        if user_id is None:
            # bad json sent in headers
            errbody= {
                'message' : f"{mylambdafunction}() - Cant find app_user_id in 'headers'"
            }
            errorresponse = {
                'statusCode': 403,
                'headers': json.dumps(getResponseHeaders()),
                'body': json.dumps( errbody )
            }
            return errorresponse

        params = {
            'TableName': tablename,
            'KeyConditionExpression': 'user_id = :uid',
            'ExpressionAttributeValues': {
                ':uid':  user_id
            },
            'Limit': limit,
            'ScanIndexForward': False

        }

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
            data = params
            logger.info("Running "+mylambdafunction+"() in testmode")
        
        response = {
            'statusCode': 200,
            'headers': json.dumps(getResponseHeaders()),
            'body': json.dumps(data,cls=DecimalEncoder)
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
            return errorresponse

'''
Route: PATCH /note

'''

def update_note_handler(event, context):
    mylambdafunction='update_notes'
    try:
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
                'headers': json.dumps(getResponseHeaders()),
                'error': f"{mylambdafunction}() - Cannot find 'body' in event",
                'event': event
            }
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
    


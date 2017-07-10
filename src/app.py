import os
import datetime
import flask
import requests
from flask_sqlalchemy import SQLAlchemy
from flask import request, redirect, url_for, render_template
from sqlalchemy import create_engine

FACEBOOK_API_MESSAGE_SEND_URL = (
    'https://graph.facebook.com/v2.6/me/messages?access_token=%s')

app = flask.Flask(__name__)

# TODO: Set environment variables appropriately.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['FACEBOOK_PAGE_ACCESS_TOKEN'] = os.environ['FACEBOOK_PAGE_ACCESS_TOKEN']
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mysecretkey')
app.config['FACEBOOK_WEBHOOK_VERIFY_TOKEN'] = 'mysecretverifytoken'


db = SQLAlchemy(app)
engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])

# Super class of individual list tables corresponding to each user interacting with the facebook page
class List(db.Model):
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True)
    list_message = db.Column(db.String(200), unique=True)

    # to keep track of if a list is done or if a DONE list is marked Undone sometimes
    status = db.Column(db.Boolean, default=False)

    # onupdate updates the datetime whenever that row is updated
    last_updated = db.Column(db.DateTime, onupdate=datetime.datetime.now)

'''
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)

class Address(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Free form address for simplicity.
    full_address = db.Column(db.String, nullable=False)

    # Connect each address to exactly one user.
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'),
                        nullable=False)
    # This adds an attribute 'user' to each address, and an attribute
    # 'addresses' (containing a list of addresses) to each user.
    user = db.relationship('User', backref='addresses')

@app.route('/')
def index():
    """Simple example handler.

    This is just an example handler that demonstrates the basics of SQLAlchemy,
    relationships, and template rendering in Flask.

    """
    # Just for demonstration purposes
    for user in User.query:  #
        print 'User %d, username %s' % (user.id, user.username)
        for address in user.addresses:
            print 'Address %d, full_address %s' % (
                address.id, address.full_address)

    # Render all of this into an HTML template and return it. We use
    # User.query.all() to obtain a list of all users, rather than an
    # iterator. This isn't strictly necessary, but just to illustrate that both
    # User.query and User.query.all() are both possible options to iterate over
    # query results.
    return render_template('index.html', users=User.query.all())
'''

@app.route('/fb_webhook', methods=['GET', 'POST'])
def fb_webhook():
    #This handler deals with incoming Facebook Messages.

    # Handle the initial handshake request.
    if flask.request.method == 'GET':
        if (flask.request.args.get('hub.mode') == 'subscribe' and
            flask.request.args.get('hub.verify_token') ==
            app.config['FACEBOOK_WEBHOOK_VERIFY_TOKEN']):
            challenge = flask.request.args.get('hub.challenge')
            return challenge
        else:
            print 'Received invalid GET request'
            return ''  # Still return a 200, otherwise FB gets upset.

    # Get the request body as a dict, parsed from JSON.
    payload = flask.request.json

    for entry in payload['entry']:
        for event in entry['messaging']:
            if 'message' not in event:
                continue
            message = event['message']
            # Ignore messages sent by us.
            if message.get('is_echo', False):
                continue
            # Ignore messages with non-text content.
            if 'text' not in message:
                continue
            sender_id = event['sender']['id']
            message_text = message['text']
            message_reply = process_message(message_text.lower(), sender_id)
            request_url = FACEBOOK_API_MESSAGE_SEND_URL % (
                app.config['FACEBOOK_PAGE_ACCESS_TOKEN'])
            requests.post(request_url,
                          headers={'Content-Type': 'application/json'},
                          json={'recipient': {'id': sender_id},
                                'message': {'text': message_reply}})

    # Return an empty response.
    return ''

def process_message(message_text, sender_id):

    # Generate a new table based on the sender ID dynamically for all the different users interacting with the page
    table_name = "List_"+sender_id
    message_reply = ''

    # Extend List table schema to access different tables based on the user interacting
    class Personal_List(List, db.Model):
        __tablename__ = table_name
        __table_args__ = {'extend_existing': True}

    # Add a list for the first time or to existing lists
    if 'add' in message_text:

        table_name = "List_"+sender_id
        class Personal_List(List, db.Model):
            __tablename__ = table_name
            __table_args__ = {'extend_existing': True}
        if not engine.dialect.has_table(engine, table_name):
            db.create_all()
            message_reply += 'User identified as creating the list for the first time.\n'
        if len(message_text.split()) > 1:
            list_text = message_text.split("add ",1)[1]
            list_record = Personal_List(list_message = list_text)
            db.session.add(list_record)
            db.session.commit()
            if list_text:
                message_reply += 'To-do item "'+ list_text +'" added to list'
        else:
            message_reply += 'Please enter a valid list entry'

        return message_reply
    
    # Display All Lists Added and Relevant message if no list available
    elif 'list done' in message_text:

        if engine.dialect.has_table(engine, table_name):
            count = 0
            #db.session.query(Personal_List).filter_by(status=True)
            for list_details in Personal_List.query.filter_by(status=True):
                message_reply += '#' + str(list_details.id) +': ' + list_details.list_message + ' (completed on ' + str(list_details.last_updated.strftime("%B %d, %Y, %H:%M")) + ')\n'    # %Z can give the timezone if required
                count += 1
            if count>0:
                message_reply = 'You have ' + str(count) + ' items marked as done:\n' + message_reply
            else:
                message_reply = 'No items marked as DONE.'
        else:
            message_reply += 'No list found. Please add using "ADD <SPACE> List Description"'
        
        return message_reply

    # Display All Lists Added and Relevant message if no list available
    elif 'list' in message_text:

        if engine.dialect.has_table(engine, table_name):
            count = 0
            for list_details in Personal_List.query:
                message_reply += '#' + str(list_details.id) +': ' + list_details.list_message + '\n'
                count += 1
            message_reply = 'You currently have ' + str(count) + ' to-do items: \n' + message_reply
        else:
            message_reply += 'No list found. Please add using "ADD <SPACE> List Description"'
        
        return message_reply

    # Logic To mark a List as done    
    elif 'done' in message_text:

        if engine.dialect.has_table(engine, table_name):
            count = 0
            if len(message_text.split()) > 1:
                list_text = message_text.split(" ")
                if str(list_text[1]) == 'done':
                    list_id = list_text[0].split("#")
                    db.session.query(Personal_List).filter_by(id=list_id[1]).update({"status": True})
                    db.session.commit()
                    message_reply += 'To-do item "'+ str(list_id[1]) +'" marked as DONE'
            else:
                message_reply += 'Please enter a valid list entry'

        else:
            message_reply += 'No list found. Please add using "ADD <SPACE> List Description"'
        
        return message_reply

    # Logic To UNDO a List which was marked done
    elif 'undo' in message_text:

        if engine.dialect.has_table(engine, table_name):
            count = 0
            if len(message_text.split()) > 1:
                list_text = message_text.split(" ")
                if str(list_text[1]) == 'undo':
                    list_id = list_text[0].split("#")
                    db.session.query(Personal_List).filter_by(id=list_id[1]).update({"status": False})
                    db.session.commit()
                    message_reply += 'To-do item "'+ str(list_id[1]) +'" marked as UNDONE'
            else:
                message_reply += 'Please enter a valid list entry'

        else:
            message_reply += 'No list found. Please add using "ADD <SPACE> List Description"'
        
        return message_reply

    # Logic To Delete a List    
    elif 'delete' in message_text:

        if engine.dialect.has_table(engine, table_name):
            count = 0
            if len(message_text.split()) > 1:
                list_text = message_text.split(" ")
                if str(list_text[1]) == 'delete':
                    list_id = list_text[0].split("#")
                    db.session.query(Personal_List).filter_by(id=list_id[1]).delete()
                    db.session.commit()
                    message_reply += 'List number "'+ str(list_id[1]) +'" is deleted.'
            else:
                message_reply += 'Please enter a valid list entry'

        else:
            message_reply += 'No list found. Please add using "ADD <SPACE> List Description"'
        
        return message_reply

    elif 'hi' in message_text:
        return 'Hey There! I am Test Bot.'
    elif 'how are you' in message_text:
        return 'Good, How about you?'
    elif 'fine' in message_text:
        return 'Cool'
    # Display all the available options to the user
    elif 'help' in message_text:
        return 'Hola!!!\nI can manage your to-do lists and track them.\n\n1. In order to add a list, you can use the format "ADD <SPACE> List Description" to add to the to-do list.\n2. Using "LIST" would list all the lists added now.\n3. Change status to DONE using the "#Listno. DONE".\n4. Change status to UNDONE using the "#Listno. UNDO".\n5. Type "List Done" to see your recent lists which were marked DONE".\n6. Type "#Listno. DELETE" to delete a list."\n\nThanks!!!'
    else:
        return 'I am unable to understand what you mean. I can give you a guideline on how I can help you with. Just type \'Help\''

'''
Just a dummy redirect to try how to add a new entry in postgresql and redirect the page

@app.route('/add_user')
def add_user():
    return render_template('add_user.html')

@app.route('/post_user', methods=['POST'])
def post_user():

    Comment to not store details of user into database and redirect to index page

    user = User(request.form['username'])
    db.session.add(user)
    db.session.commit()
    return redirect(url_for('index'))

#    return "<h1 style='color : red'>Hey there "+request.form['username']+" !!!</h1>"
'''

if __name__ == '__main__':
    app.run(debug=True)

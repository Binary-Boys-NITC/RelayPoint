from flask import Flask, request, jsonify, render_template,redirect,make_response, send_file
import base64
from datetime import datetime
import qrcode
from io import BytesIO
import json
from sqlalchemy import or_, func
import pgapp as pg
import os
from urllib.parse import quote
from datetime import timedelta

app = Flask(__name__)

def generate_qr(username, event_id, email):
    try:
        # Compact data in JSON format
        data = json.dumps({"username": username, "event_id": event_id, "email": email}, separators=(',', ':'))
        
        # Generate the QR Code
        qr = qrcode.QRCode(
            version=None,  # Auto-adjust version
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        # Create the QR image
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")  # Convert to RGB for JPG

        # Convert the image to base64 in JPG format
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.read()).decode('utf-8')

        return f"data:image/jpeg;base64,{img_base64}"
    except Exception as e:
        return f"Error generating QR code: {str(e)}"

def generate_ical(event):
    # Format datetime for IST timezone
    def format_datetime_ist(dt):
        return dt.strftime('%Y%m%dT%H%M%S')
    
    url_encoded = f"""data:text/calendar;charset=utf8,BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//BinaryBoys//RelayPoint//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VTIMEZONE
TZID:Asia/Kolkata
BEGIN:STANDARD
DTSTART:19700101T000000
TZNAME:IST
TZOFFSETFROM:+0530
TZOFFSETTO:+0530
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:{quote(str(event.id)) + quote("@relaypoint.nitc.ac.in")}
DTSTART;TZID=Asia/Kolkata:{format_datetime_ist(event.date)}
DTEND;TZID=Asia/Kolkata:{format_datetime_ist(event.date + timedelta(hours=1))}
DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:{quote(event.title)}
DESCRIPTION:{quote(event.description.replace(",", "\\,"))}
STATUS:CONFIRMED
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR""".replace("\n", "%0A")
    
    return url_encoded
    

    
@app.route('/image/<int:id>',methods=["GET"])
def image(id):
    image=pg.session.query(pg.Image).filter(pg.Image.id==id).first()
    return send_file(BytesIO(image.data),mimetype=image.mime_type)

@app.route('/',methods=['GET'])
def index():
    username=request.cookies.get("username")
    secret_key=request.cookies.get("secret_key")
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/'))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    latest=pg.session.query(pg.Event).order_by(pg.Event.date.desc()).all()[:3]

    current_datetime = datetime.now()

    upcoming_events=pg.session.query(pg.Event).filter(pg.Event.date>=current_datetime).all() 
    upcoming_events=sorted(upcoming_events,key=lambda i:i.date)
    
    if request.cookies.get("secret_key"):
        user=pg.session.query(pg.User).filter(pg.User.username==username).first()
        if user.secret_key == secret_key:
            user_stats=pg.session.query(pg.UserStats).filter(pg.UserStats.username==username).first()
            points=pg.pgGetPoints(username)
            
            registered_events=[]
            for event_id in pg.pgGetRecentEvents(username,secret_key):
                event = pg.pgGetEvent(event_id)
                if event.date>current_datetime:
                    registered_events.append(event)
            
            for event in registered_events:
                time_difference = event.date - datetime.now()
                event.time_difference = time_difference.days  # This does NOT persist in DB
            

            return render_template('home.html',
                                    username=request.cookies.get("username"),
                                    profile_link='/myprofile',
                                    points=points,
                                    rank=pg.pgGetRank(username),
                                    attended_events=len(user_stats.events_ids),
                                    upcoming_events=upcoming_events,
                                    registered_events=registered_events[::-1],
                                    latest=latest,
                                    app_stats=pg.pgAppStats()
                                    )
        else:
            pg.pgLogout(username,secret_key)
            response = make_response(redirect('/'))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    
    return render_template('home.html',
                            username="Guest User",
                            profile_link='/login',
                            latest=latest,
                            upcoming_events=upcoming_events,
                            app_stats=pg.pgAppStats())

@app.route('/login',methods=["GET"])
def login():
    if request.cookies.get("secret_key")!=None:
        return redirect('/')
    else:
        return render_template('login.html',username="Guest User",profile_link='/login')

@app.route('/signup',methods=["GET"])
def signup():
    if request.cookies.get("secret_key"):
        return redirect('/')
    else:
        return render_template('signup.html',username="Guest User",profile_link='/login')

@app.route('/api/login',methods=["POST"])
def apiLogin():
    resp = pg.pgLogin(request.form['username'],request.form['password'])
    if resp["status_code"]==200:
        secret_key=resp["secret_key"]
        response = make_response(redirect('/'))
        response.set_cookie('username',request.form['username'])
        response.set_cookie('secret_key',secret_key)
        return response
    else:
        return render_template('login.html',username="Guest User",profile_link='/login',message=resp['message'])

@app.route('/api/signup',methods=["POST"])
def apiSignup():
    if request.form['password']!=request.form['confirm_password']:
        return render_template('signup.html',username="Guest User",profile_link='/login',message="Passwords do not match")
    if os.getenv('EMAIL_DOMAIN','@nitc.ac.in') not in request.form['email']:
        return render_template('signup.html',username="Guest User",profile_link='/login',message="Invalid email")
    resp = pg.pgCreateUser(request.form['username'],request.form['password'],['student'],request.form['email'])
    if resp['status_code']==200:
        return redirect('/login')
    else:
        return render_template('signup.html',username="Guest User",profile_link='/login',message=resp['message'])

@app.route('/logout',methods=["GET"])
def logout():
    pg.pgLogout(request.cookies['username'],request.cookies['secret_key'])
    response = make_response(redirect('/login'))
    response.set_cookie('secret_key','',expires=0)
    response.set_cookie('username','',expires=0)
    return response

@app.route('/create_event',methods=['GET'])
def createEvent():
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/create_event'))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    if username==None:
        return redirect('/login')
    
    if pg.pgAuthorizeCreateEvent(username,secret_key):
        return render_template('create_event.html',username=request.cookies.get("username"),profile_link='/myprofile',auth=True)
    else:
        return render_template('create_event.html',username=request.cookies.get("username"),profile_link='/myprofile',auth=False)

@app.route('/api/create_event',methods=["POST"])
def apiCreateEvent():
    
    image_id = pg.pgUploadImage(request.files['image'])

    formdate=request.form['date']
    if pg.pgAuthorizeCreateEvent(request.cookies.get('username'),request.cookies.get('secret_key')):
        #formdate is 2025-06-17 12:00
        date={
            "year":int(formdate.split('-')[0]),
            "month":int(formdate.split('-')[1]),
            "day":int(formdate.split('-')[2].split(' ')[0]),
            "hour":int(formdate.split(' ')[1].split(':')[0]),
            "minute":int(formdate.split(' ')[1].split(':')[1]),
        }
        resp = pg.pgCreateEvent(request.cookies.get('username'),
                         request.form['eventName'],
                         request.form['description'],
                         request.form['category'],
                         date,
                         [image_id],
                         [request.cookies.get('username')],
                         registration_link=request.form['registration_link'] if request.form['registration_link'] else None
                         )
        if resp['status_code']==200:
            return redirect('/')
        else:
            return render_template('create_event.html',username=request.cookies.get("username"),profile_link='/myprofile',message=resp['message'])

@app.route('/myprofile',methods=["GET"])
def myprofile():
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/myprofile'))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    if username==None:
        return redirect('/login')
    points=pg.pgGetPoints(username)
    recent_events_ids=pg.pgGetRecentEvents(username,secret_key)
    if recent_events_ids==False:
        return redirect('/login')
    recent_events=[]
    for id in recent_events_ids:
        recent_events.append(pg.pgGetEvent(id))
        
    
    return render_template('/profile.html',
                           username=username,
                           profile_url='/myprofile',
                           workshop_count=len(recent_events_ids),
                           points=points,rank=pg.pgGetRank(username),
                           recent_events=recent_events)
@app.route('/leaderboard',methods=["GET"])
def leaderboard():
    username = request.cookies.get('username')
    secret_key= request.cookies.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/leaderboard'))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    if username==None:
        return redirect('/login')
    LB=pg.pgRanklist()
    for user in LB:
        user.pointsTotal=pg.pgGetPoints(user.username)
    return render_template('/leaderboard.html',
                           username=username,profile_link='/myprofile',
                           myrank=pg.pgGetRank(username),
                           mypoints=pg.pgGetPoints(username), 
                           myworkshops=len(pg.pgGetRecentEvents(username,secret_key)),
                           LB=LB)

@app.route('/events',methods=["GET"])
def events():
    category = request.args.get('category')
    if category==None:
        category=''
    username=request.cookies.get('username')
    if username==None:
        username="Guest User"
    current_datetime = datetime.now()

    upcoming_events = (
        pg.session.query(pg.Event)
        .filter(
            or_(func.lower(pg.Event.category) == category.lower(), category == ''),
            pg.Event.date > current_datetime
        )
        .all()
    )

    upcoming_events=sorted(upcoming_events,key=lambda i:i.date,reverse=True)
    
    return render_template('upcoming_events.html',
                           username=username,
                           profile_link="/myprofile" if username!="Guest User" else "/login",
                           upcoming_events=upcoming_events,
                           selected_category=category.lower() if category!='' else 'all')

@app.route('/myevents',methods=["GET"])
def myevents():
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/myevents'))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    if username==None:
        username="Guest User"
    my_events=[]
    if secret_key!=None:
        for event_id in pg.pgGetCreatedEvents(username,secret_key):
            event = pg.pgGetEvent(event_id)
            my_events.append(event)
    
    return render_template('upcoming_events.html',
                           username=username,
                           profile_link="/myprofile" if username!="Guest User" else "/login",
                           my_events=my_events)


@app.route('/about',methods=["GET"])
def about():
    username=request.cookies.get('username')
    if username==None:
        username="Guest User"
    return render_template('about.html',
                           username=username,
                           profile_link="/myprofile" if username!="Guest User" else "/login",)

@app.route('/community',methods=["GET"])
def community():
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/community'))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    if username==None:
        return redirect('/login')
    return render_template('community.html',username=username,profile_link='/myprofile',blogs=pg.pgGetBlogs())

@app.route('/api/post_blog',methods=["POST"])
def post_blog():
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username==None:
        return redirect('/community')
    pg.pgPostBlog(username,secret_key,request.form['blog'],datetime.now())
    return redirect('/community')
    
@app.route('/event/<int:id>',methods=["GET"])
def event(id):
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/event/'+str(id)))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    if username==None:
        return redirect('/login')
    event=pg.pgGetEvent(id)
    
    return render_template('registered.html',
                    username=(username  or "Guest User"),
                    profile_link="/myprofile" if username=="Guest User" else "/login",
                    event=event,
                    alreadyRegistered=None
                    )
    
@app.route('/register/<int:id>',methods=["GET"])
def register(id):
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/register/'+str(id)))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    if username==None:
        return redirect('/login')
    email=pg.pgUserFetch(username)['data']['email']
    event=pg.pgGetEvent(id)    
    resp = pg.pgRegisterEvent(username,secret_key,id)
    alreadyRegistered=not(resp['status_code']==200)
    if event.registration_link:
        registration_link = event.registration_link
    else:
        registration_link = None

    return render_template('registered.html',
            username=username,
            profile_link="/myprofile" if username!="Guest User" else "/login",
            event=event,
            alreadyRegistered=alreadyRegistered,
            qr=generate_qr(username,id,email),
            ical=generate_ical(event),
            registration_link=registration_link
            )

@app.route('/api/award',methods=["POST"])
def apiAward():
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username==None:
        return redirect('/login')
    resp = pg.pgAwardPoints(username,secret_key,request.form['student-name'],request.form['event-id'],request.form['points'])
    return redirect('/award/'+str(request.form['event-id']))

@app.route('/api/award_all',methods=["POST"])
def apiAwardAll():
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username==None:
        return redirect('/login')
    pg.pgAwardAllPoints(username,secret_key,request.form['event-id'],request.form['points'])
    return redirect('/award/'+str(request.form['event-id']))

@app.route('/award/<int:id>',methods=["GET"])
def award(id):
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/award/'+str(id)))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    registered_users_id=pg.pgGetEvent(id).registered_users
    registered_users=[]
    event=pg.pgGetEvent(id)
    for i in registered_users_id:
        registered_users.append(pg.pgUserFetch(i))
    return render_template('award.html',
                           username=username,
                           profile_link='/myprofile',
                           event_id=id,
                           event=event,
                           non_awarded_users=pg.pgNonAwardedUsers(id)
                           )

@app.route('/participants/<int:id>',methods=["GET"])
def participants(id):
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username==None or secret_key==None or not pg.pgAuthorizeCreateEvent(username,secret_key):
        return redirect('/login')
    return jsonify(pg.pgGetParticipants(id))

@app.route('/make_organizer',methods=["POST"])
def make_organizer():
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    
    return jsonify(pg.pgMakeOrganizer(request.form['username'],username,secret_key))

@app.route('/resetdb', methods=["GET"])
def resetdb_route():
    username = request.cookies.get('username')
    secret_key = request.cookies.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/resetdb'))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    
    if not username or not secret_key:
        return redirect('/login')
    
    try:
        result = pg.pgAdminResetDB(username, secret_key)
        pg.reinitialize_session()
        response = make_response(redirect('/login'))
        response.set_cookie('secret_key','',expires=0)
        response.set_cookie('username','',expires=0)
        return response
        
    except Exception as e:
        return jsonify({"status_code": 500, "message": f"Server error: {str(e)}"})

@app.route('/admin/import_db',methods=["POST"])
def import_db():
    return jsonify(pg.pgImportDB(request.form['username'],request.form['secret_key'],json.loads(request.files['import_file'].read())))

@app.route('/admin/export_db',methods=["GET"])
def export_db():
    return jsonify(pg.pgExportDB(request.cookies.get('username'),request.cookies.get('secret_key')))

@app.route('/admin',methods=["GET"])
def adminpage():
    username = request.cookies.get('username')
    secret_key = request.cookies.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/resetdb'))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    if username==None:
        return redirect('/login')
    if "admin" not in pg.pgUserFetch(username)['data']['roles']:
        return redirect('/')
    return render_template('admin.html',username=username,secret_key=secret_key,profile_link='/myprofile')

@app.route('/admin/whatsapp_events',methods=["GET"])
def whatsapp_events():
    username = request.args.get('username')
    secret_key = request.args.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/admin/whatsapp_events'))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    if username==None:
        return redirect('/login')
    return jsonify(pg.pgWhatsappEvents(username,secret_key))

@app.route('/admin/sent_whatsapp_event/<int:id>',methods=["GET"])
def sent_whatsapp_event(id):
    username = request.args.get('username')
    secret_key = request.args.get('secret_key')
    if username!=None:
        if not pg.pgUserAuth(username,secret_key):
            response = make_response(redirect('/admin/sent_whatsapp_event/'+str(id)))
            response.set_cookie('secret_key','',expires=0)
            response.set_cookie('username','',expires=0)
            return response
    if username==None:
        return redirect('/login')
    return jsonify(pg.pgSentWhatsappEvent(username,secret_key,id))

if __name__ == "__main__":
    app.run(host='0.0.0.0',port=os.environ.get('PORT',10000),debug=True)
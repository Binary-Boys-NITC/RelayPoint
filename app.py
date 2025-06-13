from flask import Flask, request, jsonify, render_template,redirect,make_response, send_file
import base64
from datetime import datetime
import qrcode
from io import BytesIO
import json
from sqlalchemy import or_, func
import pgapp as pg
import os

app = Flask(__name__)

def generate_qr(username, event_id):
    try:
        # Compact data in JSON format
        data = json.dumps({"username": username, "event_id": event_id}, separators=(',', ':'))
        
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

@app.route('/img_upload', methods=['POST'])
def upload_image():
    uploaded_file = request.files['image']
    binary_data=uploaded_file.read()
    mimetype = uploaded_file.mimetype
    image = pg.Image(data=binary_data, mime_type=mimetype)
    pg.session.add(image)
    pg.session.commit()
    image_id = image.id
    return {"status_code":200,"message":"Ok","id":image_id}
    
@app.route('/image/<int:id>',methods=["GET"])
def image(id):
    image=pg.session.query(pg.Image).filter(pg.Image.id==id).first()
    return send_file(BytesIO(image.data),mimetype=image.mime_type)

@app.route('/',methods=['GET'])
def index():
    username=request.cookies.get("username")
    secret_key=request.cookies.get("secret_key")
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
                                    registered_events=registered_events,
                                    latest=latest,
                                    app_stats=pg.pgAppStats()
                                    )
    
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
    if "@nitc.ac.in" not in request.form['email']:
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
    if request.cookies.get('username')!=None:
        roles=pg.pgUserFetch(request.cookies.get('username'))["data"]["roles"]
        if "organizer" in roles or "admin" in roles:
            return render_template('create_event.html',username=request.cookies.get("username"),profile_link='/myprofile',auth=True)
        else:
            return render_template('create_event.html',username=request.cookies.get("username"),profile_link='/myprofile',auth=False)
        
    else:
        return redirect('/login')

@app.route('/api/create_event',methods=["POST"])
def apiCreateEvent():
    binary_data=request.files['image'].read()
    mimetype=request.files['image'].mimetype
    image_id=pg.pgUploadImage(binary_data,mimetype)
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
                         [request.cookies.get('username')]
                         )
        if resp['status_code']==200:
            return redirect('/')
        else:
            return render_template('create_event.html',username=request.cookies.get("username"),profile_link='/myprofile',message=resp['message'])

@app.route('/myprofile',methods=["GET"])
def myprofile():
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
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
    return render_template('about.html')

@app.route('/community',methods=["GET"])
def community():
    username=request.cookies.get('username')
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
    if username==None:
        return redirect('/login')
    event=pg.pgGetEvent(id)     #(id,title,description,category,date,imageids,organizers,access,registered_users)
    resp = pg.pgRegisterEvent(username,secret_key,id)
    alreadyRegistered=not(resp['status_code']==200)
    
    return render_template('registered.html',
                    username=username,
                    profile_link="/myprofile" if username!="Guest User" else "/login",
                    event=event,
                    alreadyRegistered=alreadyRegistered,
                    qr=generate_qr(username,id)
                    )

@app.route('/api/award',methods=["POST"])
def apiAward():
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    if username==None:
        return redirect('/login')
    resp = pg.pgAwardPoints(username,secret_key,request.form['student-name'],request.form['event-id'],request.form['points'])
    return redirect('/award/'+str(request.form['event-id']))

@app.route('/award/<int:id>',methods=["GET"])
def award(id):
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
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

@app.route('/make_organizer',methods=["GET"])
def make_organizer():
    username=request.cookies.get('username')
    secret_key=request.cookies.get('secret_key')
    return jsonify(pg.pgMakeOrganizer(request.args.get('user'),username,secret_key))

@app.route('/test',methods=["GET"])
def test():
    return render_template('award.html')
if __name__ == "__main__":
    app.run(host='0.0.0.0',port=os.environ.get('PORT',10000),debug=True)
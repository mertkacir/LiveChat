from flask_sqlalchemy import SQLAlchemy
from flask import Flask, render_template, request, session, redirect, url_for,jsonify
from flask_socketio import join_room, leave_room, send, SocketIO
import random
from datetime import datetime, timezone
utc_now = datetime.now(timezone.utc)
from marshmallow import Schema, fields, post_load
from string import ascii_uppercase
from itertools import permutations

db = SQLAlchemy()
app = Flask(__name__)

app.config["SECRET_KEY"] = "hjhjsdahhds"
socketio = SocketIO(app)
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(255), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    sender_name = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<Message {self.id}>"

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # ... diğer Room model sütunları eklenebilir

    def __repr__(self):
        return f"<Room {self.id}>"

class MessageSchema(Schema):
    id = fields.Integer(dump_only=True)
    content = fields.String()
    room_id = fields.Integer()
    sender_name = fields.String()
    created_at = fields.DateTime(dump_only=True)

    @post_load
    def create_message(self, data, **kwargs):
        return Message(**data)

def init_db():
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
    db.init_app(app)

    with app.app_context():
        db.create_all()

rooms = {}

def generate_unique_code(length):
    while True:
        code = ""
        for _ in range(length):
            code += random.choice(ascii_uppercase)
        
        if code not in rooms:
            break
    
    return code

@app.route("/", methods=["POST", "GET"])
def home():
    session.clear()
    if request.method == "POST":
        name = request.form.get("name")
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)

        if not name:
            return render_template("home.html", error="Lütfen isminizi giriniz.", code=code, name=name)

        if join != False and not code:
            return render_template("home.html", error="Lütfen Oda numarasını giriniz.", code=code, name=name)
        
        room = code
        if create != False:
            room = generate_unique_code(4)
            rooms[room] = {"members": 0, "messages": []}
        elif code not in rooms:
            return render_template("home.html", error="Böyle bir oda yok.", code=code, name=name)
        
        session["room"] = room
        session["name"] = name
        return redirect(url_for("room"))

    return render_template("home.html")

@app.route("/room")
def room():
    room = session.get("room")
    if room is None or session.get("name") is None or room not in rooms:
        return redirect(url_for("home"))

    return render_template("room.html", code=room, messages=rooms[room]["messages"])




@socketio.on("message")
def message(data):
    room = session.get("room")
    if room not in rooms:
        return 
    content = {
        "name": session.get("name"),
        "message": data["data"]
    }
    send(content, to=room)
    rooms[room]["messages"].append(content)
    # Save message to database
    message = Message(content=data["data"],
                      room_id=room,
                      sender_name=session.get("name"))
    db.session.add(message)
    db.session.commit()
    print(f"{session.get('name')} said: {data["data"]}")



@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = session.get("name")
    if not room or not name:
        return
    if room not in rooms:
        leave_room(room)
        return
    
    join_room(room)
    send({"name": name, "message": "odaya katıldı."}, to=room)
    rooms[room]["members"] += 1
    print(f"{name} odaya katıldı {room}")

@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]
    
    send({"name": name, "message": "odadan çıktı."}, to=room)
    print(f"{name} odadan çıktı {room}")



@app.route("/api/messages/<string:room_id>", methods=["GET"])
def get_messages_by_room(room_id):
    """
    API endpoint to retrieve chat history for a specific room.
    """
    room_id_lower = room_id.lower()
    with app.app_context():
        room_messages = Message.query.filter_by(room_id=room_id_lower).all()
        if not room_messages:
            return jsonify(["Test"])  # Veritabanında mesaj yoksa boş bir liste döndür

        schema = MessageSchema(many=True)
        return jsonify(schema.dump(room_messages))
if __name__ == "__main__":
    init_db()
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)

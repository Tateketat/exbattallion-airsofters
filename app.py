import os
import secrets
from datetime import datetime
from flask import (
    Flask, render_template, redirect, url_for, flash,
    session, request, abort, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from authlib.integrations.flask_client import OAuth
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey

db = SQLAlchemy()

# --- Config ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-super-long-secret-key'  # Change this!
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://exbattallion_db_user:s914i2N36DVKp3Yl05TPUsf18MOmBJC5@dpg-d42vnkh5pdvs73dhtgs0-a.singapore-postgres.render.com/exbattallion_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# --- OAuth Setup ---
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id='3642994520-9jji3ql411hq2henrt24i8be19bo28o8.apps.googleusercontent.com',
    client_secret='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',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# --- Models ---
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    callsign = db.Column(db.String(64))
    role = db.Column(db.String(64))
    team = db.Column(db.String(64))
    bio = db.Column(db.Text)
    aeg = db.Column(db.String(64))  # Added aeg field for profile
    profile_image = db.Column(db.String(255))
    loadouts = relationship(
        'Loadout',
        back_populates='user',
        cascade="all, delete-orphan",
        passive_deletes=True
    )

class Team(db.Model):
    __tablename__ = 'teams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    city = db.Column(db.String(64))
    description = db.Column(db.Text)

class Loadout(db.Model):
    __tablename__ = 'loadouts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(128))
    type = db.Column(db.String(64))
    notes = db.Column(db.Text)
    aeg_image = db.Column(db.String(255))  # <--- NEW FIELD
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = relationship('User', back_populates='loadouts')
    images = relationship('LoadoutImage', back_populates='loadout', cascade='all, delete-orphan')

class LoadoutImage(db.Model):
    __tablename__ = 'loadout_images'
    id = db.Column(db.Integer, primary_key=True)
    loadout_id = db.Column(db.Integer, db.ForeignKey('loadouts.id', ondelete="CASCADE"), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    loadout = relationship('Loadout', back_populates='images')

# --- Auth Decorator ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# --- Helper Functions ---
def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def save_image(file_storage):
    if file_storage and allowed_image(file_storage.filename):
        filename = secure_filename(file_storage.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        unique_name = f"{secrets.token_hex(8)}.{ext}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file_storage.save(file_path)
        return unique_name
    return None

def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def get_user_by_id(user_id):
    if user_id:
        return User.query.get(user_id)
    return None

app.jinja_env.globals.update(get_user=get_user_by_id)

def get_users_with_latest_loadout_image():
    users = User.query.all()
    result = []
    for user in users:
        # Get the latest loadout with an image
        latest_loadout = (
            Loadout.query.filter_by(user_id=user.id)
            .order_by(Loadout.created_at.desc())
            .first()
        )
        if latest_loadout:
            latest_img = (
                LoadoutImage.query.filter_by(loadout_id=latest_loadout.id)
                .order_by(LoadoutImage.id.desc())
                .first()
            )
            if latest_img:
                result.append({
                    "user": user,
                    "loadout_img": latest_img.image_path,
                    "loadout": latest_loadout
                })
    return result

# --- Routes ---
@app.route('/')
def home():
    teams = Team.query.all()
    name = request.args.get('name')  # filter by name/callsign/email
    type_ = request.args.get('type')
    role = request.args.get('role')

    # Instagram grid: show latest loadout image per user
    users_with_loadouts = get_users_with_latest_loadout_image()

    # Filtering for gallery/list
    query = Loadout.query.order_by(Loadout.created_at.desc())
    if name:
        query = query.join(User).filter(
            (User.callsign.ilike(f"%{name}%")) | (User.email.ilike(f"%{name}%"))
        )
    if type_:
        query = query.filter(Loadout.type == type_)
    if role:
        query = query.join(User).filter(User.role == role)
    loadouts = query.all()

    # Per-user loadout: for Add/Edit button logic
    user_loadout = None
    user_has_loadout = False
    if 'user_id' in session:
        user_loadout = Loadout.query.filter_by(user_id=session['user_id']).first()
        user_has_loadout = user_loadout is not None

    # Only ONE render_template! Pass users_with_loadouts for grid.
    return render_template(
        'home.html',
        users_with_loadouts=users_with_loadouts,
        teams=teams,
        loadouts=loadouts,
        selected_type=type_,
        selected_role=role,
        user_has_loadout=user_has_loadout,
        user_loadout=user_loadout
    )

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()
    userinfo = None
    try:
        userinfo = google.parse_id_token(token)
    except Exception as e:
        print("parse_id_token error:", e)
    if not userinfo:
        userinfo_endpoint = google.server_metadata['userinfo_endpoint']
        resp = google.get(userinfo_endpoint, token=token)
        userinfo = resp.json()
    email = userinfo.get('email')
    if not email:
        flash("Google login failed: no email found.", "danger")
        return redirect(url_for('home'))
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email)
        db.session.add(user)
        db.session.commit()
    session['user_id'] = user.id
    flash('Logged in as %s' % email, 'success')
    return redirect(url_for('profile'))  # <-- Redirects to Create Profile page

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = get_current_user()
    if not user:
        session.clear()
        flash("Your session has expired or your user was deleted. Please log in again.", "danger")
        return redirect(url_for('login'))
    teams = Team.query.all()
    if request.method == 'POST':
        user.callsign = request.form.get('callsign')
        user.role = request.form.get('role')
        user.team = request.form.get('team')
        user.bio = request.form.get('bio')
        user.aeg = request.form.get('aeg')
        if 'loadout_image' in request.files:
            img = request.files['loadout_image']
            if img and allowed_image(img.filename):
                img_name = save_image(img)
                user.profile_image = img_name  # Always save to profile_image!
        db.session.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('home'))
    return render_template('profile.html', user=user, teams=teams)

@app.route('/add-loadout', methods=['GET', 'POST'])
@login_required
def add_loadout():
    user = get_current_user()
    # --- Only allow one loadout per user ---
    existing = Loadout.query.filter_by(user_id=user.id).first()
    if existing:
        flash("You already have a loadout, you can only edit it.", "warning")
        return redirect(url_for('edit_loadout', loadout_id=existing.id))
    if request.method == 'POST':
        # Get form fields
        type_ = request.form.get('type')
        role = request.form.get('role')
        notes = request.form.get('notes')

        # Handle AEG (Rifle) image upload
        aeg_image_file = request.files.get('aeg_image')
        aeg_image_name = None
        if aeg_image_file and aeg_image_file.filename and allowed_image(aeg_image_file.filename):
            aeg_image_name = save_image(aeg_image_file)

        # Handle main loadout image (required)
        img = request.files.get('loadout_picture')
        if not img or img.filename == '':
            flash('Please select a loadout picture.', 'danger')
            return redirect(url_for('add_loadout'))
        if not allowed_image(img.filename):
            flash('Invalid image type. Allowed: png, jpg, jpeg, gif, webp', 'danger')
            return redirect(url_for('add_loadout'))
        img_name = save_image(img)
        if not img_name:
            flash('Error saving image. Try again.', 'danger')
            return redirect(url_for('add_loadout'))

        # Create Loadout object
        loadout = Loadout(
            user_id=user.id,
            type=type_,
            notes=notes,
            aeg_image=aeg_image_name,  # Save rifle picture
            title=type_ + " Loadout" if type_ else "Loadout",
            created_at=datetime.utcnow()
        )
        db.session.add(loadout)
        db.session.flush()  # So loadout.id available

        # Save main loadout image
        loadout_image = LoadoutImage(loadout_id=loadout.id, image_path=img_name)
        db.session.add(loadout_image)
        db.session.commit()

        flash('Loadout uploaded!', 'success')
        return redirect(url_for('home'))
    return render_template('add_loadout.html')

@app.route('/edit-loadout/<int:loadout_id>', methods=['GET', 'POST'])
@login_required
def edit_loadout(loadout_id):
    user = get_current_user()
    loadout = Loadout.query.get_or_404(loadout_id)
    if loadout.user_id != user.id:
        abort(403)
    if request.method == 'POST':
        type_ = request.form.get('type')
        notes = request.form.get('notes')

        loadout.type = type_
        loadout.notes = notes

        # Handle AEG (Rifle) image upload
        aeg_image_file = request.files.get('aeg_image')
        if aeg_image_file and aeg_image_file.filename and allowed_image(aeg_image_file.filename):
            aeg_image_name = save_image(aeg_image_file)
            loadout.aeg_image = aeg_image_name

        # Handle main loadout image (optional update)
        img = request.files.get('loadout_picture')
        if img and img.filename and allowed_image(img.filename):
            img_name = save_image(img)
            # Delete old images if you want (optional)
            # For now, just add a new one
            loadout_image = LoadoutImage(loadout_id=loadout.id, image_path=img_name)
            db.session.add(loadout_image)

        db.session.commit()
        flash('Loadout updated!', 'success')
        return redirect(url_for('home'))
    return render_template('edit_loadout.html', loadout=loadout)

@app.route('/loadout/<int:loadout_id>')
def loadout_detail(loadout_id):
    loadout = Loadout.query.get_or_404(loadout_id)
    user = User.query.get(loadout.user_id)
    return render_template('loadout_detail.html', loadout=loadout, user=user)

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.context_processor
def inject_now():
    return {'now': datetime.now(timezone.utc)}

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, threaded=False)
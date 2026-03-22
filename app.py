import os
import random
import string
from datetime import datetime

from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ── Database ────────────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///spinning.db')
# Railway supplies postgres:// but SQLAlchemy requires postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ── Admin password (set via Railway env var ADMIN_PASSWORD) ─────
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'spinning')

# ── Models ──────────────────────────────────────────────────────
class CourseDate(db.Model):
    __tablename__ = 'dates'
    id          = db.Column(db.String(32), primary_key=True)
    datetime_str = db.Column(db.String(32), nullable=False)
    label       = db.Column(db.String(200), default='')

class Signup(db.Model):
    __tablename__ = 'signups'
    id         = db.Column(db.String(32), primary_key=True)
    name       = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SignupDate(db.Model):
    __tablename__ = 'signup_dates'
    signup_id = db.Column(db.String(32), db.ForeignKey('signups.id'), primary_key=True)
    date_id   = db.Column(db.String(32), db.ForeignKey('dates.id'),   primary_key=True)

# ── Helper ──────────────────────────────────────────────────────
def uid():
    return datetime.now().strftime('%Y%m%d%H%M%S') + ''.join(
        random.choices(string.ascii_lowercase + string.digits, k=5)
    )

def check_admin(data):
    return data and data.get('password') == ADMIN_PASSWORD

# ── Routes ──────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

# — Dates —
@app.route('/api/dates', methods=['GET'])
def get_dates():
    rows = CourseDate.query.order_by(CourseDate.datetime_str).all()
    return jsonify([{'id': r.id, 'datetime': r.datetime_str, 'label': r.label} for r in rows])

@app.route('/api/dates', methods=['POST'])
def add_date():
    data = request.get_json()
    if not check_admin(data):
        return jsonify({'error': 'Non autorisé'}), 401
    new = CourseDate(id=uid(), datetime_str=data['datetime'], label=data.get('label', ''))
    db.session.add(new)
    db.session.commit()
    return jsonify({'id': new.id, 'datetime': new.datetime_str, 'label': new.label}), 201

@app.route('/api/dates/<date_id>', methods=['DELETE'])
def delete_date(date_id):
    data = request.get_json()
    if not check_admin(data):
        return jsonify({'error': 'Non autorisé'}), 401
    SignupDate.query.filter_by(date_id=date_id).delete()
    CourseDate.query.filter_by(id=date_id).delete()
    db.session.commit()
    return jsonify({'ok': True})

# — Signups —
@app.route('/api/signups', methods=['GET'])
def get_signups():
    rows = Signup.query.order_by(Signup.created_at).all()
    result = []
    for s in rows:
        date_ids = [sd.date_id for sd in SignupDate.query.filter_by(signup_id=s.id).all()]
        result.append({'id': s.id, 'name': s.name, 'dates': date_ids})
    return jsonify(result)

@app.route('/api/signups', methods=['POST'])
def add_signup():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    selected = data.get('dates') or []
    if not name:
        return jsonify({'error': 'Nom requis'}), 400
    if not selected:
        return jsonify({'error': 'Aucune séance sélectionnée'}), 400

    # Update if name already exists (case-insensitive)
    existing = Signup.query.filter(db.func.lower(Signup.name) == name.lower()).first()
    if existing:
        signup_id = existing.id
        SignupDate.query.filter_by(signup_id=signup_id).delete()
    else:
        signup_id = uid()
        db.session.add(Signup(id=signup_id, name=name))

    for date_id in selected:
        db.session.add(SignupDate(signup_id=signup_id, date_id=date_id))

    db.session.commit()
    return jsonify({'id': signup_id, 'name': name, 'dates': selected}), 201

@app.route('/api/signups/<signup_id>', methods=['DELETE'])
def delete_signup(signup_id):
    data = request.get_json()
    if not check_admin(data):
        return jsonify({'error': 'Non autorisé'}), 401
    SignupDate.query.filter_by(signup_id=signup_id).delete()
    Signup.query.filter_by(id=signup_id).delete()
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/signups/all', methods=['DELETE'])
def clear_signups():
    data = request.get_json()
    if not check_admin(data):
        return jsonify({'error': 'Non autorisé'}), 401
    SignupDate.query.delete()
    Signup.query.delete()
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/reset', methods=['POST'])
def reset_all():
    data = request.get_json()
    if not check_admin(data):
        return jsonify({'error': 'Non autorisé'}), 401
    SignupDate.query.delete()
    Signup.query.delete()
    CourseDate.query.delete()
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/auth', methods=['POST'])
def check_auth():
    data = request.get_json()
    if check_admin(data):
        return jsonify({'ok': True})
    return jsonify({'error': 'Mot de passe incorrect'}), 401

# ── Startup ─────────────────────────────────────────────────────
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

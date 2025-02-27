import os
import csv
from io import StringIO
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from io import StringIO, BytesIO

app = Flask(__name__)
# Use environment variable SECRET_KEY for security; fallback for local testing.
app.secret_key = os.environ.get('SECRET_KEY', 'fallback_secret')

# Use DATABASE_URL from Render if available; otherwise, fallback to SQLite.
db_url = os.environ.get('DATABASE_URL', 'sqlite:///discussion.db')
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ----------------------------
# Models
# ----------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(300), nullable=False)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    upvote_count = db.Column(db.Integer, default=0)
    parent_id = db.Column(db.Integer, db.ForeignKey('review.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('reviews', lazy=True))
    # For replies, use a dynamic relationship so we can order them
    replies = db.relationship('Review', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')

class Upvote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    review_id = db.Column(db.Integer, db.ForeignKey('review.id'), nullable=False)

# ----------------------------
# Routes
# ----------------------------
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('discussion'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists. Please choose another.')
            return redirect(url_for('register'))
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful. Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('discussion'))
        else:
            flash('Invalid username or password.')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.')
    return redirect(url_for('login'))

@app.route('/discussion')
def discussion():
    if 'user_id' not in session:
        flash('Please login first.')
        return redirect(url_for('login'))
    reviews = Review.query.filter_by(parent_id=None).all()
    return render_template('discussion.html', reviews=reviews, Review=Review)

@app.route('/post_review', methods=['POST'])
def post_review():
    if 'user_id' not in session:
        flash('Please log in to post.')
        return redirect(url_for('login'))
    text = request.form['text'].strip()
    parent_id = request.form.get('parent_id')
    parent_id = int(parent_id) if parent_id and parent_id.isdigit() else None
    new_review = Review(text=text, user_id=session['user_id'], parent_id=parent_id)
    db.session.add(new_review)
    db.session.commit()
    return redirect(url_for('discussion'))

@app.route('/upvote/<int:review_id>', methods=['POST'])
def upvote(review_id):
    if 'user_id' not in session:
        flash('Please log in to upvote.')
        return redirect(url_for('login'))
    user_id = session['user_id']
    if Upvote.query.filter_by(user_id=user_id, review_id=review_id).first():
        flash('You have already upvoted this post.')
        return redirect(url_for('discussion'))
    new_vote = Upvote(user_id=user_id, review_id=review_id)
    db.session.add(new_vote)
    review = Review.query.get(review_id)
    review.upvote_count += 1
    db.session.commit()
    return redirect(url_for('discussion'))

@app.route('/export_csv')
def export_csv():
    if 'user_id' not in session:
        flash('Please log in to export data.')
        return redirect(url_for('login'))
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['review_id', 'text', 'upvotes', 'comments'])
    main_reviews = Review.query.filter_by(parent_id=None).all()
    for review in main_reviews:
        replies = review.replies.order_by(Review.id).all()
        comments = " | ".join([f"{review.id}.{idx+1}: {reply.text}" for idx, reply in enumerate(replies)])
        cw.writerow([review.id, review.text, review.upvote_count, comments])
    si.seek(0)
    output = BytesIO(si.getvalue().encode('utf-8'))
    output.seek(0)
    
    return send_file(output, mimetype="text/csv", as_attachment=True, download_name="reviews.csv")
# ----------------------------
# Initialize Database Tables
# ----------------------------
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)

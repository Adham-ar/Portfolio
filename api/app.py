import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, URL, Optional
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from dotenv import load_dotenv

# Load the environment variables from the hidden .env file
load_dotenv()

# --- VERCEL COMPATIBLE FOLDER PATHS & INSTANCE BLOCK ---
if os.environ.get('VERCEL') == '1':
    # Tell Flask to look up one level into the root directory for front-end templates & static files
    app = Flask(__name__,
                instance_path='/tmp',
                template_folder='../templates',
                static_folder='../static')
else:
    app = Flask(__name__, instance_path='/tmp')

# --- SECURED CONFIGURATIONS ---
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'fallback-dev-key')

if os.environ.get('VERCEL') == '1':
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/portfolio.db'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///portfolio.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- SMTP MAIL CONFIGURATIONS ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False

app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

# Initialize extensions safely to prevent early default folder construction
db = SQLAlchemy()
db.init_app(app)

mail = Mail(app)

# --- AUTOMATIC DATABASE TABLES CREATION ON FIRST VISIT ---
@app.before_request
def create_tables():
    # This runs right before the first request hits, creating tables if they are missing
    db.create_all()

# --- LOGIN SETUP ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# --- MODELS ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    tech_stack = db.Column(db.String(200), nullable=False)
    github_url = db.Column(db.String(200), nullable=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- FORMS ---

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class ProjectForm(FlaskForm):
    title = StringField('Project Title', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired()])
    tech_stack = StringField('Tech Stack (comma-separated)', validators=[DataRequired()])
    github_url = StringField('GitHub URL', validators=[Optional(), URL()])
    submit = SubmitField('Save Project')


def add_tags_to_projects(projects):
    for project in projects:
        project.tags = [tech.strip() for tech in project.tech_stack.split(',')]


# --- ROUTES ---

@app.route('/')
def home():
    projects = Project.query.order_by(Project.date_created.desc()).all()
    add_tags_to_projects(projects)
    return render_template('home.html', projects=projects)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/contact', methods=['POST'])
def contact():
    name = request.form.get('name')
    email = request.form.get('email')
    message_content = request.form.get('message')

    if name and email and message_content:
        try:
            msg = Message(
                subject=f"Portfolio Contact: {name}",
                recipients=[os.environ.get('MAIL_USERNAME')],
                reply_to=email
            )
            msg.body = f"New portfolio message from:\nName: {name}\nEmail: {email}\n\nMessage:\n{message_content}"
            mail.send(msg)
            flash('Thank you! Your message has been sent directly to my inbox.', 'contact_success')
        except Exception as e:
            print(f"Mail sending failed: {e}")
            flash('Oops! Something went wrong on the server. Please try again later.', 'contact_error')
    else:
        flash('Please fill out all fields before submitting.', 'contact_error')

    return redirect(url_for('home') + '#contact')


# --- PROTECTED CRUD ROUTES ---

@app.route('/admin')
@login_required
def admin_dashboard():
    projects = Project.query.order_by(Project.date_created.desc()).all()
    return render_template('admin.html', projects=projects)


@app.route('/admin/project/new', methods=['GET', 'POST'])
@login_required
def new_project():
    form = ProjectForm()
    if form.validate_on_submit():
        new_item = Project(
            title=form.title.data,
            description=form.description.data,
            tech_stack=form.tech_stack.data,
            github_url=form.github_url.data
        )
        db.session.add(new_item)
        db.session.commit()
        return redirect(url_for('admin_dashboard'))
    return render_template('project_form.html', form=form, title="Add New Project")


@app.route('/admin/project/edit/<int:project_id>', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    form = ProjectForm(obj=project)

    if form.validate_on_submit():
        project.title = form.title.data
        project.description = form.description.data
        project.tech_stack = form.tech_stack.data
        project.github_url = form.github_url.data
        db.session.commit()
        return redirect(url_for('admin_dashboard'))

    return render_template('project_form.html', form=form, title="Edit Project")


@app.route('/admin/project/delete/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    app.run(debug=True)
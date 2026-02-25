from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
import os
import requests

# -----------------------------
# FLASK APP INIT
# -----------------------------
app = Flask(__name__)

app.config["SECRET_KEY"] = "partify-secret-key"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(BASE_DIR, "instance", "partify.db")
os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACKING_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"


# -----------------------------
# MODELS
# -----------------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    company = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    contact = db.Column(db.String(200), nullable=False)

    category = db.Column(db.String(50), default="other")  # ⭐ NEW FIELD

    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))

    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    db.create_all()


# -----------------------------
# GEOCODING
# -----------------------------
def geocode_location(address):
    if not address:
        return None, None

    addr = address.strip()
    if "india" not in addr.lower():
        addr += ", India"

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": addr, "format": "json", "limit": 1}
    headers = {"User-Agent": "PartifyApp"}

    try:
        res = requests.get(url, params=params, headers=headers, timeout=5)
        res.raise_for_status()
        data = res.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except:
        pass

    return None, None


# -----------------------------
# INDEX PAGE
# -----------------------------
@app.route("/")
def index():
    jobs = Job.query.order_by(Job.id.desc()).limit(5).all()
    return render_template("home.html", jobs=jobs)


# -----------------------------
# JOB LIST PAGE (CATEGORY + SEARCH)
# -----------------------------
@app.route("/jobs")
def jobs_list():
    category = request.args.get("category")
    search = request.args.get("search", "").strip()

    query = Job.query

    if category:
        query = query.filter_by(category=category)

    if search:
        query = query.filter(Job.title.ilike(f"%{search}%"))

    jobs = query.order_by(Job.id.desc()).all()

    categories = ["tuition", "cafe", "mall", "operator", "office", "other"]

    return render_template(
        "jobs.html",
        jobs=jobs,
        categories=categories,
        selected_category=category,
        search=search,
    )


# -----------------------------
# JOB DETAIL PAGE
# -----------------------------
@app.route("/job/<int:job_id>")
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)

    google_maps_url = None
    if job.latitude and job.longitude:
        google_maps_url = f"https://www.google.com/maps?q={job.latitude},{job.longitude}"

    return render_template(
        "job_detail.html",
        job=job,
        google_maps_url=google_maps_url
    )


# -----------------------------
# POST JOB
# -----------------------------
@app.route("/post-job", methods=["GET", "POST"])
@login_required
def post_job():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        company = request.form.get("company", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        contact = request.form.get("contact", "").strip()
        category = request.form.get("category", "other")

        lat, lng = geocode_location(location)

        job = Job(
            title=title,
            company=company,
            location=location,
            description=description,
            contact=contact,
            category=category,
            created_by=current_user.id,
            latitude=lat,
            longitude=lng,
        )

        db.session.add(job)
        db.session.commit()

        flash("Job posted successfully!", "success")
        return redirect(url_for("jobs_list"))

    return render_template("post_job.html")


# -----------------------------
# EDIT JOB
# -----------------------------
@app.route("/edit-job/<int:job_id>", methods=["GET", "POST"])
@login_required
def edit_job(job_id):
    job = Job.query.get_or_404(job_id)

    if job.created_by != current_user.id:
        flash("Not allowed!", "error")
        return redirect(url_for("my_jobs"))

    if request.method == "POST":
        job.title = request.form.get("title", "").strip()
        job.company = request.form.get("company", "").strip()
        job.location = request.form.get("location", "").strip()
        job.description = request.form.get("description", "").strip()
        job.contact = request.form.get("contact", "").strip()
        job.category = request.form.get("category", "other")

        job.latitude, job.longitude = geocode_location(job.location)

        db.session.commit()
        flash("Job updated!", "success")
        return redirect(url_for("my_jobs"))

    return render_template("edit_job.html", job=job)


# -----------------------------
# DELETE JOB
# -----------------------------
@app.route("/delete-job/<int:job_id>")
@login_required
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)

    if job.created_by != current_user.id:
        flash("Not allowed!", "error")
        return redirect(url_for("my_jobs"))

    db.session.delete(job)
    db.session.commit()

    flash("Job deleted.", "success")
    return redirect(url_for("my_jobs"))


# -----------------------------
# MY JOBS
# -----------------------------
@app.route("/my-jobs")
@login_required
def my_jobs():
    jobs = Job.query.filter_by(created_by=current_user.id).all()
    return render_template("my_jobs.html", jobs=jobs)


# -----------------------------
# AUTH
# -----------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email").lower()
        password = request.form.get("password")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for("login"))

        user = User(name=name, email=email)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash("Signup successful! Login now.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").lower()
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash("Logged in!", "success")
            return redirect(url_for("index"))

        flash("Invalid login details.", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "success")
    return redirect(url_for("index"))


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)

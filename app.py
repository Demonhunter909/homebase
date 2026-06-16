import os
import datetime
import time
import math
from flask import Flask, flash, redirect, render_template, request, session, send_from_directory, url_for, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import timedelta
from uuid import uuid4
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__, static_folder='.', static_url_path='')

# Session configuration - use Flask's built-in secure cookies
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_NAME"] = "session"
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Set to False for development over HTTP, True for HTTPS in production
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "False").lower() == "true"
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-2026-change-in-production")

# Configure upload folder
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


@app.before_request
def make_session_permanent():
    session.permanent = True

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("user_id") is None:
            flash("You must be logged in", "error")
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

def get_paginated_category(category, page, per_page=16):
    start = (page - 1) * per_page

    response = (
        supabase.table("uploads")
        .select("*")
        .eq("category", category)
        .order("created_at", desc=True)
        .range(start, start + per_page)
        .execute()
    )

    count_response = (
        supabase.table("uploads")
        .select("id", count="exact")
        .eq("category", category)
        .execute()
    )

    total_items = count_response.count
    total_pages = math.ceil(total_items / per_page)
    return response.data, total_pages

def get_paginated_all(page, per_page=16):
    start = (page - 1) * per_page

    response = (
        supabase.table("uploads")
        .select("*")
        .order("created_at", desc=True)
        .range(start, start + per_page)
        .execute()
    )

    count_response = (
        supabase.table("uploads")
        .select("id", count="exact")
        .execute()
    )

    total_items = count_response.count
    total_pages = math.ceil(total_items / per_page)
    return response.data, total_pages

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            flash("Email and password required", "error")
            return redirect("/login")
        
        result = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if not result.user:
            flash("Invalid email or password", "error")
            return redirect("/login")
        
        session["user"] = {
            "id": result.user.id,
            "email": result.user.email
        }
        flash(f"Welcome back, {email}!", "success")
        return redirect("/")
    return render_template("login.html", username=session.get("user", {}).get("email"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirm_password")

        if not email or not username or not password or not confirm:
            flash("All fields required", "error")
            return redirect("/register")

        if password != confirm:
            flash("Passwords do not match", "error")
            return redirect("/register")

        result = supabase.auth.sign_up({
            "email": email,
            "password": password
        })

        if result.user is None:
            flash("Email already exists", "error")
            return redirect("/register")

        profile_insert = supabase.table("profiles").insert({
            "id": result.user.id,
            "username": username,
            "parent_id": session.get("user", {}).get("id")
        })

        if profile_insert.error:
            flash("Profile creation failed: " + profile_insert.error.message, "error")
            return redirect("/register")

        session["user"] = {
            "id": result.user.id,
            "email": email
        }

        flash(f"Account created successfully! Welcome, {username}!", "success")
        return redirect("/")

    return render_template("register.html", username=session.get("user", {}).get("email"))


@app.route("/logout")
def logout():
    supabase.auth.sign_out()
    session.clear()
    flash("You have been logged out", "success")
    return redirect("/")

@app.route("/")
def index():
    page = int(request.args.get("page", 1))
    uploads, total_pages = get_paginated_category("home", page)

    return render_template("index.html", uploads=uploads, page=page, total_pages=total_pages, username=session.get("user"))


@app.route("/pricing")
def pricing():
    page = int(request.args.get("page", 1))
    uploads, total_pages = get_paginated_category("pricing", page)

    return render_template("pricing.html", uploads=uploads, page=page, total_pages=total_pages, username=session.get("user"))


@app.route("/library")
def library():
    page = int(request.args.get("page", 1))
    uploads, total_pages = get_paginated_category("library", page)

    return render_template("library.html", uploads=uploads, page=page, total_pages=total_pages, username=session.get("user"))

@app.route("/about")
def about():
    page = int(request.args.get("page", 1))
    uploads, total_pages = get_paginated_category("about", page)
    
    return render_template("about.html", uploads=uploads, page=page, total_pages=total_pages, username=session.get("user"))

@app.route("/adminpanel")
@login_required
def adminpanel():
    page = int(request.args.get("page", 1))
    uploads, total_pages = get_paginated_all(page)
    return render_template("adminpanel.html", username=session.get("user"), uploads=uploads, page=page, total_pages=total_pages)


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        url = request.form.get("url")
        category = request.form.get("category")
        image = request.files.get("cover_image")

        if not url or not category or not title or not image:
            flash("Title, URL, category and cover image required", "error")
            return redirect("/upload")

        # Secure filename
        filename = secure_filename(image.filename)
        unique_name = f"{uuid4()}-{filename}"

        # Read file bytes
        file_bytes = image.read()
        upload_result = supabase.storage.from_("uploads").upload(unique_name, file_bytes)

        # Handle upload error
        if isinstance(upload_result, dict) and "error" in upload_result:
            flash("Failed to upload image to storage", "error")
            return redirect("/upload")

        # Get public URL
        public_url = supabase.storage.from_("uploads").get_public_url(unique_name)

        # Save metadata + public image URL in Neon DB
        supabase.table("uploads").insert({
            "url": url,
            "category": category,
            "user_id": session["user"]["id"],
            "title": title,
            "description": description,
            "cover_image": public_url
        })

        flash("URL uploaded successfully!", "success")
        if category == "home":
            return redirect("/")
        else:
            return redirect(f"/{category}")

    # GET request: load existing uploads + slideshow
    uploads = (
        supabase.table("uploads")
        .select("*")
        .order("created_at", desc=True)
    ).data

    return render_template("adminpanel.html", username=session.get("user"), uploads=uploads)
  
@app.route("/delete-url/<int:url_id>")
@login_required
def delete_url(url_id):
    row = (
        supabase.table("uploads")
        .select("category")
        .eq("id", url_id)
    ).data

    if not row:
        flash("URL not found", "error")
        return redirect("/")

    category = row["category"]

    supabase.table("uploads").delete().eq("id", url_id)

    flash("URL deleted", "success")
    if category == "home":
        return redirect("/")
    else:
        return redirect(f"/{category}")

@app.route("/edit-url/<int:url_id>", methods=["GET", "POST"])
@login_required
def edit_url(url_id):

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        url = request.form.get("url")

        row = (
            supabase.table("uploads")
            .select("category")
            .eq("id", url_id)
        ).data

        category = row["category"]

        supabase.table("uploads").update({
            "title": title,
            "description": description,
            "url": url
        }).eq("id", url_id)

        flash("URL updated!", "success")
        if category == "home":
            return redirect("/")
        else:
            return redirect(f"/{category}")

    item = (
        supabase.table("uploads")
        .select("*")
        .eq("id", url_id)
    ).data

    if not item:
        flash("URL not found", "error")
        return redirect("/")

    return render_template("edit_url.html", item=item, url_id=url_id, username=session.get("user"))

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
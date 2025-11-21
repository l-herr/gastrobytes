import json

from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from bson import ObjectId
import os
import pymongo
import requests
from bs4 import BeautifulSoup
import urllib.request
import json
import urllib.request
import os
from flask import session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "your_secret_key_here"
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

client = pymongo.MongoClient("mongodb://localhost:27017")
db = client["recipesdb_plain"]
recipes_col = db["recipes"]
users_col = db["users"]

if not users_col.find_one({"role": "admin"}):
    users_col.insert_one({
        "username": "admin",
        "password": generate_password_hash("admin123"),
        "role": "admin"
    })
    print("Created default admin: username=admin, password=admin123")

def recipe_to_dict(doc):
    return {
        "_id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "ingredients": doc.get("ingredients", []),
        "steps": doc.get("steps", []),
        "image_filename": doc.get("image_filename")
    }
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def scrape_allrecipes(url):
    response = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    })
    soup = BeautifulSoup(response.text, "html.parser")


    data_script = soup.find("script", type="application/ld+json")
    if not data_script:
        raise ValueError("Recipe data not found on page.")

    data = json.loads(data_script.string)


    if isinstance(data, list):
        data = data[0]

    name = data.get("name", "Untitled Recipe")


    ingredients = data.get("recipeIngredient", [])


    steps = []
    for step in data.get("recipeInstructions", []):
        if isinstance(step, dict) and "text" in step:
            steps.append(step["text"].strip())
        elif isinstance(step, str):
            steps.append(step.strip())


    image_filename = None
    img_url = None


    image_data = data.get("image")
    if isinstance(image_data, list):
        img_url = image_data[0]
    elif isinstance(image_data, str):
        img_url = image_data

    if img_url:
        img_url = img_url.split("?")[0]
        image_filename = os.path.basename(img_url)
        try:
            urllib.request.urlretrieve(img_url, os.path.join(app.config["UPLOAD_FOLDER"], image_filename))
        except:
            image_filename = None

    return name, ingredients, steps, image_filename

@app.route("/")
@login_required
def index():
    if session.get("role") != "admin":
        docs = list(recipes_col.find({"user_id": session["user_id"]}).sort("_id", -1))
    else:
        docs = list(recipes_col.find().sort("_id", -1))

    recipes = [recipe_to_dict(d) for d in docs]
    return render_template("index.html", recipes=recipes)

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        url = request.form.get("scrape_url", "").strip()
        if url:
            name, ingredients, steps, filename = scrape_allrecipes(url)
        else:
            name = request.form.get("name", "")
            ingredients = [line.strip() for line in request.form.get("ingredients").splitlines() if line.strip()]
            steps = [line.strip() for line in request.form.get("steps", "").splitlines() if line.strip()]
            image = request.files.get("image")
            filename = None
            if image and image.filename:
                filename = secure_filename(image.filename)
                image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        doc = {
            "name": name,
            "ingredients": ingredients,
            "steps": steps,
            "image_filename": filename,
            "user_id": session.get("user_id")
        }

        recipes_col.insert_one(doc)
        return redirect(url_for("index"))

    return render_template("add.html")


@app.route("/edit/<rid>", methods=["GET", "POST"])
def edit(rid):
    recipe = recipes_col.find_one({"_id": ObjectId(rid)})
    if not recipe:
        return "Recipe not found", 404

    if request.method == "POST":
        name = request.form.get("name", "")
        ingredients = [line.strip() for line in request.form.get("ingredients", "").splitlines() if line.strip()]
        steps = [line.strip() for line in request.form.get("steps", "").splitlines() if line.strip()]
        update = {"name": name, "ingredients": ingredients, "steps": steps}

        image = request.files.get("image")
        if image and image.filename:
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            update["image_filename"] = filename

        recipes_col.update_one({"_id": ObjectId(rid)}, {"$set": update})
        return redirect(url_for("index"))

    recipe = recipe_to_dict(recipe)
    return render_template("edit.html", recipe=recipe)

@app.route("/delete/<rid>", methods=["POST"])
def delete(rid):
    try:
        recipes_col.delete_one({"_id": ObjectId(rid)})
    except Exception:
        return "Error deleting recipe", 400
    return redirect(url_for("index"))



def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = users_col.find_one({"_id": ObjectId(session.get("user_id", ""))})
        if not user or user.get("role") != "admin":
            flash("Admin access required.")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password").strip()

        if users_col.find_one({"username": username}):
            flash("Username already exists.")
            return redirect(url_for("register"))

        hashed_pw = generate_password_hash(password)
        users_col.insert_one({"username": username, "password": hashed_pw, "role": "user"})
        flash("Registration successful! Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = users_col.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            session["username"] = user["username"]
            session["role"] = user.get("role", "user")
            flash("Logged in successfully!")
            return redirect(url_for("index"))
        flash("Invalid credentials.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def admin_panel():
    users = list(users_col.find())
    return render_template("admin.html", users=users)

@app.route("/admin/edit/<uid>", methods=["GET", "POST"])
@admin_required
def admin_edit_user(uid):
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        flash("User not found.")
        return redirect(url_for("admin_panel"))

    if request.method == "POST":
        new_username = request.form.get("username").strip()
        new_role = request.form.get("role")
        new_password = request.form.get("password")

        update_data = {
            "username": new_username,
            "role": new_role
        }

        if new_password:
            update_data["password"] = generate_password_hash(new_password)

        users_col.update_one({"_id": ObjectId(uid)}, {"$set": update_data})
        flash("User updated successfully.")
        return redirect(url_for("admin_panel"))

    return render_template("admin_edit_user.html", user=user)

@app.route("/admin/delete_user/<uid>", methods=["POST"])
@admin_required
def admin_delete_user(uid):
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        flash("User not found.")
        return redirect(url_for("admin_panel"))

    # Prevent deleting yourself
    if str(user["_id"]) == session.get("user_id"):
        flash("You cannot delete your own account.")
        return redirect(url_for("admin_panel"))

    # Prevent deleting last admin
    if user.get("role") == "admin":
        admin_count = users_col.count_documents({"role": "admin"})
        if admin_count <= 1:
            flash("You cannot delete the last administrator.")
            return redirect(url_for("admin_panel"))

    users_col.delete_one({"_id": ObjectId(uid)})
    flash("User deleted successfully.")
    return redirect(url_for("admin_panel"))



if __name__ == "__main__":
    app.run(debug=True)

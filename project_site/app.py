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

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

client = pymongo.MongoClient("mongodb://localhost:27017")
db = client["recipesdb_plain"]
recipes_col = db["recipes"]

def recipe_to_dict(doc):
    return {
        "_id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "ingredients": doc.get("ingredients", []),
        "steps": doc.get("steps", []),
        "image_filename": doc.get("image_filename")
    }


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
def index():
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
            "image_filename": filename
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

if __name__ == "__main__":
    app.run(debug=True)

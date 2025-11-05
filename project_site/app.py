from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from bson import ObjectId
from datetime import datetime
import os
import pymongo

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
        name = request.form.get("name", "")
        ingredients = [line.strip() for line in request.form.get("ingredients", "").splitlines() if line.strip()]
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
            "created_at": datetime.utcnow()
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

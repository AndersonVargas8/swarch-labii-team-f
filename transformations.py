import os
import textwrap


def generate_database(name):
    path = f'skeleton/{name}'
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, 'init.sql'), 'w') as f:
        f.write(textwrap.dedent("""
            CREATE TABLE IF NOT EXISTS systems (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255)
            );
        """))

def generate_doc_database(name):
    path = f'skeleton/{name}'
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, 'init.js'), 'w') as f:
        f.write(textwrap.dedent(f"""
            db = db.getSiblingDB('{name}');
            db.createCollection("documents");
        """))


def generate_backend(name, database, docDatabase=None):
    path = f'skeleton/{name}'
    os.makedirs(path, exist_ok=True)

    # --- Generar app.py ---
    with open(os.path.join(path, 'app.py'), 'w') as f:
        imports = ["from flask import Flask, request, jsonify"]
        init_code = []
        routes = []

        # ---- Conexión relacional (MySQL) ----
        if database:
            imports.append("import mysql.connector")
            init_code.append(f"""
def get_mysql_conn():
    return mysql.connector.connect(
        host='{database}',
        user='root',
        password='root',
        database='{database}'
    )
""")

            routes.append("""
@app.route('/systems', methods=['GET'])
def get_systems():
    conn = get_mysql_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM systems")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(systems=rows)

@app.route('/create', methods=['POST'])
def create_system():
    data = request.json
    conn = get_mysql_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO systems (name) VALUES (%s)", (data['name'],))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify(status="created")
""")

        # ---- Conexión documental (MongoDB) ----
        if docDatabase:
            imports.append("from pymongo import MongoClient")
            init_code.append(f"""
mongo_client = MongoClient('mongodb://{docDatabase}:27017/')
mongo_db = mongo_client['{docDatabase}']
""")

            routes.append("""
@app.route('/documents', methods=['GET'])
def get_documents():
    docs = list(mongo_db.documents.find({}, {'_id': 0}))
    return jsonify(documents=docs)

@app.route('/documents', methods=['POST'])
def create_document():
    data = request.json
    mongo_db.documents.insert_one(data)
    return jsonify(status="inserted")
""")

        # ---- Ensamblar aplicación completa ----
        imports_code = "\n".join(imports)
        init_code_block = "\n".join(init_code)
        routes_code = "\n".join(routes)

        app_code = textwrap.dedent(f"""\
{imports_code}

app = Flask(__name__)

{init_code_block}

{routes_code}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
""")

        f.write(app_code)

    # --- Generar Dockerfile ---
    with open(os.path.join(path, 'Dockerfile'), 'w') as f:
        deps = "flask mysql-connector-python"
        if docDatabase:
            deps += " pymongo"

        dockerfile_code = f"""\
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install {deps}
CMD ["python", "app.py"]
"""
        f.write(dockerfile_code)
        
def generate_frontend(name, backend, hasDocDatabase=False):
    path = f'skeleton/{name}'
    os.makedirs(path, exist_ok=True)

    # --- package.json ---
    with open(os.path.join(path, 'package.json'), 'w') as f:
        f.write(textwrap.dedent("""
            {
                "name": "frontend",
                "version": "1.0.0",
                "main": "app.js",
                "dependencies": {
                    "express": "^4.18.2",
                    "axios": "^1.6.7"
                }
            }
        """))

    # --- Dockerfile ---
    with open(os.path.join(path, 'Dockerfile'), 'w') as f:
        f.write(textwrap.dedent("""
            FROM node:18
            WORKDIR /app
            COPY . .
            RUN npm install
            CMD ["node", "app.js"]
        """))

    # --- app.js ---
    with open(os.path.join(path, 'app.js'), 'w') as f:
        base_code = f"""
            const express = require('express');
            const axios = require('axios');
            const app = express();

            app.use(express.json());
            app.use(express.urlencoded({{ extended: true }}));

            const BACKEND_URL = 'http://{backend}:80';

            // Página principal: muestra sistemas y documentos (si aplica)
            app.get('/', async (req, res) => {{
                try {{
                    let html = `
                        <html>
                            <body>
                                <h1>Frontend</h1>
                                <h2>Systems</h2>
                                <form method="POST" action="/create-system">
                                    <input name="name" placeholder="System name"/>
                                    <button type="submit">Create</button>
                                </form>
                    `;

                    const systemsResponse = await axios.get(`${{BACKEND_URL}}/systems`);
                    const systems = systemsResponse.data.systems || [];
                    const systemList = systems.map(([id, name]) => `<li>${{name}}</li>`).join('');
                    html += `<ul>${{systemList}}</ul>`;
        """

        # --- Agregar sección documental si aplica ---
        if hasDocDatabase:
            base_code += textwrap.dedent("""
                    html += `
                        <h2>Documents</h2>
                        <form method="POST" action="/create-document">
                            <input name="title" placeholder="Document title"/>
                            <input name="content" placeholder="Document content"/>
                            <button type="submit">Add</button>
                        </form>
                    `;
                    try {
                        const docsResponse = await axios.get(`${BACKEND_URL}/documents`);
                        const docs = docsResponse.data.documents || [];
                        const docList = docs.map(d => `<li><b>${d.title}</b>: ${d.content}</li>`).join('');
                        html += `<ul>${docList}</ul>`;
                    } catch (err) {
                        html += `<p><i>Error fetching documents</i></p>`;
                    }
            """)

        base_code += """
                    html += `</body></html>`;
                    res.send(html);
                } catch (err) {
                    console.error(err);
                    res.status(500).send("Error contacting backend");
                }
            });

            // --- Endpoints para crear sistemas y documentos ---
            app.post('/create-system', async (req, res) => {
                const name = req.body.name;
                await axios.post(`${BACKEND_URL}/create`, { name });
                res.redirect('/');
            });
        """

        # --- Endpoint para crear documentos ---
        if hasDocDatabase:
            base_code += textwrap.dedent("""
                app.post('/create-document', async (req, res) => {
                    const { title, content } = req.body;
                    await axios.post(`${BACKEND_URL}/documents`, { title, content });
                    res.redirect('/');
                });
            """)

        # --- Cierre ---
        base_code += """
            app.listen(80, () => console.log("Frontend running on port 80"));
        """

        f.write(textwrap.dedent(base_code))


def generate_docker_compose(components):
    path = 'skeleton/'
    os.makedirs(path, exist_ok=True)

    with open(os.path.join(path, 'docker-compose.yml'), 'w') as f:
        sorted_components = dict(sorted(
            components.items(),
            key=lambda item: 0 if item[1] in ("database", "docDatabase") else 1
        ))

        f.write("services:\n")

        db = None
        for i, (name, ctype) in enumerate(sorted_components.items()):
            port = 8000 + i
            f.write(f"  {name}:\n")

            if ctype == "database":
                db = name
                f.write("    image: mysql:8\n")
                f.write("    environment:\n")
                f.write("      - MYSQL_ROOT_PASSWORD=root\n")
                f.write(f"      - MYSQL_DATABASE={name}\n")
                f.write("    volumes:\n")
                f.write(f"      - ./{name}/init.sql:/docker-entrypoint-initdb.d/init.sql\n")
                f.write("    ports:\n")
                f.write("      - '3306:3306'\n")
            elif ctype == "docDatabase":
                db = name
                f.write("    image: mongo:7\n")
                f.write("    environment:\n")
                f.write(f"      - MONGO_INITDB_DATABASE={name}\n")
                f.write("    volumes:\n")
                f.write(f"      - ./{name}/init.js:/docker-entrypoint-initdb.d/init.js\n")
                f.write("    ports:\n")
                f.write("      - '27017:27017'\n")
            else:
                f.write(f"    build: ./{name}\n")
                f.write(f"    ports:\n")
                f.write(f"      - '{port}:80'\n")
                if ctype == "backend" and db:
                    f.write("    depends_on:\n")
                    f.write(f"      - {db}\n")

        f.write("\nnetworks:\n  default:\n    driver: bridge\n")


def apply_transformations(model):
    components = {}
    backend_name = None
    database_name = None
    doc_database_name = None

    for e in model.elements:
        if e.__class__.__name__ == 'Component':
            if e.type == 'backend':
                backend_name = e.name
            elif e.type == 'database':
                database_name = e.name
            elif e.type == 'docDatabase':
                doc_database_name = e.name

    for e in model.elements:
        if e.__class__.__name__ == 'Component':
            components[e.name] = e.type
            if e.type == 'database':
                generate_database(e.name)
            elif e.type == 'docDatabase':
                generate_doc_database(e.name)
            elif e.type == 'backend':
                generate_backend(e.name, database=database_name, docDatabase=doc_database_name)
            elif e.type == 'frontend':
                generate_frontend(e.name, backend=backend_name, hasDocDatabase=True)

    generate_docker_compose(components)

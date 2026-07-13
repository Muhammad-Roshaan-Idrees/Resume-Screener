
import os
import re
import zipfile
from io import BytesIO
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, send_file, session
from werkzeug.utils import secure_filename
import pdfplumber
import docx
from PIL import Image
import pytesseract

# ------------------------------
#  Flask App Configuration
# ------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change_this_in_production")  # CHANGE THIS in production!
app.config['SESSION_TYPE'] = 'filesystem'

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
ALLOWED_EXTENSIONS = {"pdf", "docx", "jpg", "jpeg", "png", "webp"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Check Tesseract availability
try:
    pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
except:
    TESSERACT_AVAILABLE = False
    print("WARNING: Tesseract OCR not found. Image text extraction will be limited.")

# Debug flag – set to True for detailed console output
DEBUG = False   # Set to False for production

import sqlite3

# ------------------------------
#  DATABASE SETUP
# ------------------------------
DB_PATH = os.path.join(os.getcwd(), "resume_screening.db")

def init_db():

    #Initialize the database with required tables.
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Create candidates table
    c.execute('''
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            status TEXT NOT NULL,
            degree TEXT,
            subject TEXT,
            job_category TEXT,
            experience TEXT,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            extracted_text TEXT
        )
    ''')
    
    # Create filters table (to save filter presets)
    c.execute('''
        CREATE TABLE IF NOT EXISTS saved_filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filter_name TEXT NOT NULL,
            degree TEXT,
            subject TEXT,
            job_category TEXT,
            experience TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def save_candidate(name, filename, filepath, status, degree="", subject="", job_category="", experience="", extracted_text=""):
    """Save candidate to database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO candidates (name, filename, filepath, status, degree, subject, job_category, experience, extracted_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, filename, filepath, status, degree, subject, job_category, experience, extracted_text))
    conn.commit()
    last_id = c.lastrowid
    conn.close()
    return last_id

def get_all_candidates():
    """Retrieve all candidates from database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, filename, filepath, status, degree, subject, job_category, experience, upload_date FROM candidates ORDER BY upload_date DESC")
    rows = c.fetchall()
    conn.close()
    
    # Convert to list of dicts
    candidates = []
    for row in rows:
        candidates.append({
            'id': row[0],
            'name': row[1],
            'filename': row[2],
            'filepath': row[3],
            'status': row[4],
            'degree': row[5],
            'subject': row[6],
            'job_category': row[7],
            'experience': row[8],
            'upload_date': row[9]
        })
    return candidates

def delete_candidate_by_id(candidate_id):
    """Delete a candidate from database and remove file."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get filepath first
    c.execute("SELECT filepath FROM candidates WHERE id = ?", (candidate_id,))
    result = c.fetchone()
    
    if result:
        filepath = result[0]
        # Delete from database
        c.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
        conn.commit()
        conn.close()
        
        # Delete file if exists
        if os.path.exists(filepath):
            os.remove(filepath)
        return True
    else:
        conn.close()
        return False

def get_filter_stats():
    """Get statistics from database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM candidates")
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM candidates WHERE status = 'Accepted'")
    accepted = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM candidates WHERE status = 'Rejected'")
    rejected = c.fetchone()[0]
    
    conn.close()
    
    return {
        'total': total,
        'accepted': accepted,
        'rejected': rejected
    }

def save_filter_preset(name, degree, subject, job_category, experience):
    """Save filter preset to database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO saved_filters (filter_name, degree, subject, job_category, experience)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, degree, subject, job_category, experience))
    conn.commit()
    conn.close()

def get_filter_presets():
    """Retrieve saved filter presets."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, filter_name, degree, subject, job_category, experience FROM saved_filters ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    
    presets = []
    for row in rows:
        presets.append({
            'id': row[0],
            'name': row[1],
            'degree': row[2],
            'subject': row[3],
            'job_category': row[4],
            'experience': row[5]
        })
    return presets

# Initialize database on startup
init_db()
print("✅ Database initialized successfully at:", DB_PATH)


# ------------------------------
#  DICTIONARIES (COMPACT + GLOBAL)
# ------------------------------

# 1. GENERIC DEGREES – only generic names in dropdown, but variations cover all specialisations
GENERIC_DEGREES = {
    'B.Sc': {
        'variations': [
            'bsc', 'b.sc', 'bachelor of science', 'bs', 'b.s',
            'bscs', 'b.s.cs', 'bs cs', 'bachelor of science in computer science',
            'bs computer science', 'b.sc computer science',
            'bsse', 'b.s.se', 'bs se', 'bachelor of science in software engineering',
            'bs software engineering', 'b.sc software engineering',
            'bs ai', 'bscs ai', 'b.s.ai', 'bachelor of science in artificial intelligence',
            'bs artificial intelligence', 'b.sc ai',
            'bsds', 'b.s.ds', 'bs ds', 'bachelor of science in data science',
            'bs data science', 'b.sc data science',
            'bscy', 'b.s.cy', 'bs cy', 'bachelor of science in cybersecurity',
            'bs cybersecurity', 'b.sc cybersecurity',
            'bsit', 'b.s.it', 'bs it', 'bachelor of science in information technology',
            'bs information technology', 'b.sc it',
            'bsce', 'b.s.ce', 'bs ce', 'bachelor of science in computer engineering',
            'bs computer engineering', 'b.sc computer engineering',
            'bca', 'b.c.a', 'bachelor of computer applications',
            'bsc hons', 'b.sc hons', 'bachelor of science honours',
            'basc', 'b.a.sc', 'bachelor of applied science',
            'bs hons', 'b.s hons', 'bachelor of science honours',
            'bsc tech', 'b.sc tech', 'bachelor of science in technology',
            'bsc agriculture', 'b.sc agriculture', 'bachelor of science in agriculture',
            'bs agriculture',
            'bsc forestry', 'b.sc forestry', 'bachelor of science in forestry',
            'bsc environmental science', 'b.sc environmental science',
            'bachelor of science in environmental science',
            'bsc nursing', 'b.sc nursing', 'bachelor of science in nursing',
            'bs nursing',
            'bsc physics hons', 'bachelor of science in physics honours',
            'bsc chemistry hons', 'bachelor of science in chemistry honours',
            'bsc mathematics hons', 'bachelor of science in mathematics honours',
            'bsc statistics hons', 'bachelor of science in statistics honours',
            'mscs', 'm.s.cs', 'ms cs', 'master of science in computer science',
            'ms computer science', 'm.sc computer science',
            'msse', 'm.s.se', 'ms se', 'master of science in software engineering',
            'ms software engineering', 'm.sc software engineering',
            'msds', 'm.s.ds', 'ms ds', 'master of science in data science',
            'ms data science', 'm.sc data science',
            'msai', 'm.s.ai', 'ms ai', 'master of science in artificial intelligence',
            'ms artificial intelligence', 'm.sc ai',
            'msit', 'm.s.it', 'ms it', 'master of science in information technology',
            'ms information technology', 'm.sc it',
            'msce', 'm.s.ce', 'ms ce', 'master of science in computer engineering',
            'ms computer engineering', 'm.sc computer engineering',
            'msc hons', 'm.sc hons', 'master of science honours',
            'masc', 'm.a.sc', 'master of applied science',
            'ms hons', 'm.s hons', 'master of science honours',
            'msc tech', 'm.sc tech', 'master of science in technology',
            'msc agriculture', 'm.sc agriculture', 'master of science in agriculture',
            'ms agriculture',
            'msc forestry', 'm.sc forestry', 'master of science in forestry',
            'msc environmental science', 'm.sc environmental science',
            'master of science in environmental science',
            'msc nursing', 'm.sc nursing', 'master of science in nursing',
            'ms nursing',
            'msc physics', 'master of science in physics',
            'msc chemistry', 'master of science in chemistry',
            'msc mathematics', 'master of science in mathematics',
            'msc statistics', 'master of science in statistics',
            'msceng', 'm.sc.eng', 'master of science in engineering',
            'b.s. eng', 'bachelor of science in engineering',
            'bs eng', 'b.s. eng',
            'ms eng', 'm.s. eng', 'master of science in engineering'
        ],
        'keywords': ['science', 'research', 'computing', 'engineering', 'technology']
    },
    'B.A.': {
        'variations': [
            'ba', 'b.a', 'bachelor of arts', 'ba in', 'b.a. in',
            'ba hons', 'b.a hons', 'bachelor of arts honours',
            'blitt', 'b.litt', 'bachelor of literature',
            'bphil', 'b.phil', 'bachelor of philosophy',
            'bfa', 'b.f.a', 'bachelor of fine arts',
            'bmus', 'b.mus', 'bachelor of music',
            'ma', 'm.a', 'master of arts', 'ma in', 'm.a. in',
            'ma hons', 'm.a hons', 'master of arts honours',
            'mlitt', 'm.litt', 'master of literature',
            'mphil', 'm.phil', 'master of philosophy',
            'mfa', 'm.f.a', 'master of fine arts',
            'mmus', 'm.mus', 'master of music',
            'maed', 'm.a.ed', 'master of arts in education'
        ],
        'keywords': ['arts', 'humanities', 'literature', 'philosophy', 'fine arts']
    },
    'B.Ed': {
        'variations': [
            'bed', 'b.ed', 'bachelor of education', 'bs education', 'b.sc education',
            'med', 'm.ed', 'master of education', 'ms education', 'm.sc education',
            'edd', 'ed.d', 'doctor of education',
            'msed', 'm.s.ed', 'master of science in education'
        ],
        'keywords': ['education', 'teaching', 'pedagogy']
    },
    'B.Com': {
        'variations': [
            'bcom', 'b.com', 'bachelor of commerce', 'bs commerce', 'b.sc commerce',
            'mcom', 'm.com', 'master of commerce', 'ms commerce', 'm.sc commerce',
            'bbs', 'b.b.s', 'bachelor of business studies',
            'bms', 'b.m.s', 'bachelor of management studies',
            'mbs', 'm.b.s', 'master of business studies',
            'mms', 'm.m.s', 'master of management studies'
        ],
        'keywords': ['commerce', 'business', 'accounting', 'finance']
    },
    'BBA': {
        'variations': [
            'bba', 'b.b.a', 'bachelor of business administration',
            'bs business administration', 'b.sc business',
            'bba hons', 'b.b.a hons', 'bachelor of business administration honours',
            'mba', 'm.b.a', 'master of business administration',
            'ms business administration', 'm.sc business',
            'executive mba', 'emba', 'e-mba',
            'pgdm', 'post graduate diploma in management',
            'pgp', 'post graduate programme',
            'dba', 'd.b.a', 'doctor of business administration'
        ],
        'keywords': ['business', 'management', 'administration', 'leadership']
    },
    'B.Tech': {
        'variations': [
            'b.tech', 'btech', 'bachelor of technology', 'bachelor in technology',
            'b tech', 'bt',
            'btech hons', 'b.tech hons', 'bachelor of technology honours',
            'b.e.', 'be', 'bachelor of engineering', 'bachelor in engineering',
            'b eng', 'beng',
            'be hons', 'b.e hons', 'bachelor of engineering honours',
            'beng hons', 'b.eng hons', 'bachelor of engineering honours',
            'm.tech', 'mtech', 'master of technology', 'master in technology',
            'm tech', 'mt',
            'm.e.', 'me', 'master of engineering', 'master in engineering',
            'm eng', 'meng',
            'meng', 'm.eng', 'master of engineering'
        ],
        'keywords': ['technology', 'engineering']
    },
    'B.Arch': {
        'variations': [
            'barch', 'b.arch', 'bachelor of architecture', 'bs architecture', 'b.sc architecture',
            'march', 'm.arch', 'master of architecture', 'ms architecture', 'm.sc architecture'
        ],
        'keywords': ['architecture', 'building design']
    },
    'B.Des': {
        'variations': [
            'bdes', 'b.des', 'bachelor of design', 'bs design', 'b.sc design',
            'bfa design', 'b.f.a design', 'bachelor of fine arts in design',
            'mdes', 'm.des', 'master of design', 'ms design', 'm.sc design',
            'mfa design', 'm.f.a design', 'master of fine arts in design'
        ],
        'keywords': ['design', 'creative', 'fine arts']
    },
    'B.Pharm': {
        'variations': [
            'bpharm', 'b.pharm', 'bachelor of pharmacy', 'bs pharmacy', 'b.sc pharmacy',
            'mpharm', 'm.pharm', 'master of pharmacy', 'ms pharmacy', 'm.sc pharmacy',
            'pharmd', 'pharm.d', 'doctor of pharmacy'
        ],
        'keywords': ['pharmacy', 'pharmaceutical', 'drugs']
    },
    'MBBS': {
        'variations': [
            'mbbs', 'm.b.b.s', 'bachelor of medicine', 'bachelor of surgery',
            'medical doctor', 'md', 'm.d', 'doctor of medicine',
            'do', 'd.o', 'doctor of osteopathic medicine'
        ],
        'keywords': ['medicine', 'medical', 'clinical', 'healthcare']
    },
    'BDS': {
        'variations': [
            'bds', 'b.d.s', 'bachelor of dental surgery', 'dental surgeon',
            'dds', 'd.d.s', 'doctor of dental surgery',
            'dmd', 'd.m.d', 'doctor of dental medicine'
        ],
        'keywords': ['dental', 'dentistry', 'oral']
    },
    'BPT': {
        'variations': [
            'bpt', 'b.p.t', 'bachelor of physiotherapy',
            'dpt', 'd.p.t', 'doctor of physical therapy',
            'mpt', 'm.p.t', 'master of physiotherapy'
        ],
        'keywords': ['physiotherapy', 'physical therapy', 'rehab']
    },
    'BOT': {
        'variations': [
            'bot', 'b.o.t', 'bachelor of occupational therapy',
            'otd', 'o.t.d', 'doctor of occupational therapy',
            'mot', 'm.o.t', 'master of occupational therapy'
        ],
        'keywords': ['occupational therapy', 'rehabilitation']
    },
    'LLB': {
        'variations': [
            'llb', 'l.l.b', 'bachelor of laws', 'bachelor of law', 'll.b',
            'llm', 'l.l.m', 'master of laws', 'master of law', 'll.m',
            'jd', 'j.d', 'juris doctor',
            'jsd', 'j.s.d', 'doctor of juridical science',
            'sjd', 's.j.d', 'doctor of juridical science'
        ],
        'keywords': ['law', 'legal', 'juris']
    },
    'Ph.D': {
        'variations': [
            'phd', 'ph.d', 'doctor of philosophy', 'doctorate', 'ph.d.',
            'd.sc', 'd.sc', 'doctor of science',
            'd.litt', 'd.litt', 'doctor of letters',
            'edd', 'ed.d', 'doctor of education',
            'aud', 'au.d', 'doctor of audiology',
            'psyd', 'psy.d', 'doctor of psychology'
        ],
        'keywords': ['doctorate', 'research', 'academic']
    },
}

# 2. SUBJECTS (Specializations) – comprehensive list with variations
SUBJECTS = {
    'Computer Science': {
        'variations': ['computer science', 'cs', 'compsci', 'comp sci', 'computing', 'cse', 'computer science and engineering'],
        'keywords': ['programming', 'algorithms', 'data structures', 'software']
    },
    'Software Engineering': {
        'variations': ['software engineering', 'se', 'software dev', 'software development', 'software engineering and management'],
        'keywords': ['software', 'development', 'agile', 'scrum']
    },
    'Artificial Intelligence': {
        'variations': ['artificial intelligence', 'ai', 'machine learning', 'ml', 'deep learning', 'intelligent systems', 'cognitive computing'],
        'keywords': ['neural networks', 'nlp', 'computer vision', 'learning']
    },
    'Data Science': {
        'variations': ['data science', 'data analytics', 'data analysis', 'big data', 'analytics', 'data engineering'],
        'keywords': ['analytics', 'statistics', 'python', 'r', 'sql', 'visualization']
    },
    'Cybersecurity': {
        'variations': ['cybersecurity', 'cyber security', 'information security', 'network security', 'computer security', 'cyber defence'],
        'keywords': ['security', 'encryption', 'firewall', 'penetration testing']
    },
    'Cloud Computing': {
        'variations': ['cloud computing', 'cloud', 'aws', 'azure', 'gcp', 'cloud architecture', 'cloud services'],
        'keywords': ['cloud', 'devops', 'container', 'kubernetes', 'docker']
    },
    'Web Development': {
        'variations': ['web development', 'web dev', 'frontend', 'backend', 'full stack', 'web application development'],
        'keywords': ['html', 'css', 'javascript', 'react', 'angular', 'vue', 'node.js']
    },
    'Mobile Development': {
        'variations': ['mobile development', 'app development', 'android', 'ios', 'mobile app', 'cross-platform'],
        'keywords': ['flutter', 'react native', 'kotlin', 'swift', 'java']
    },
    'Machine Learning': {
        'variations': ['machine learning', 'ml', 'deep learning', 'ai', 'statistical learning'],
        'keywords': ['supervised learning', 'unsupervised learning', 'tensorflow', 'pytorch']
    },
    'Database Systems': {
        'variations': ['database systems', 'database management', 'dbms', 'data management', 'relational databases', 'nosql'],
        'keywords': ['sql', 'oracle', 'mysql', 'postgresql', 'mongodb']
    },
    'Computer Networks': {
        'variations': ['computer networks', 'networking', 'network engineering', 'network design', 'communication networks'],
        'keywords': ['network', 'tcp/ip', 'routing', 'switching', 'cisco']
    },
    'Information Technology': {
        'variations': ['information technology', 'it', 'information systems', 'it management', 'information and communication technology'],
        'keywords': ['it', 'information', 'systems', 'infrastructure']
    },
    'Human-Computer Interaction': {
        'variations': ['human-computer interaction', 'hci', 'user experience', 'ux', 'user interface', 'interaction design'],
        'keywords': ['user', 'interface', 'experience', 'usability']
    },
    'Computer Graphics': {
        'variations': ['computer graphics', 'cg', 'visual computing', 'rendering', 'animation', 'graphics programming'],
        'keywords': ['graphics', 'rendering', '3d', 'animation']
    },
    'Embedded Systems': {
        'variations': ['embedded systems', 'embedded engineering', 'iot', 'internet of things', 'real-time systems'],
        'keywords': ['embedded', 'iot', 'microcontroller', 'real-time']
    },
    'Robotics': {
        'variations': ['robotics', 'robotics engineering', 'automation', 'mechatronics'],
        'keywords': ['robot', 'automation', 'control', 'sensor']
    },
    'Game Development': {
        'variations': ['game development', 'game design', 'game programming', 'game art', 'game engineering'],
        'keywords': ['game', 'unity', 'unreal', 'game design']
    },
    'Software Testing': {
        'variations': ['software testing', 'quality assurance', 'qa', 'test engineering', 'software quality'],
        'keywords': ['testing', 'qa', 'quality', 'automation']
    },
    'DevOps': {
        'variations': ['devops', 'dev ops', 'site reliability', 'sre'],
        'keywords': ['devops', 'ci/cd', 'automation', 'infrastructure']
    },
    'Mechanical Engineering': {
        'variations': ['mechanical engineering', 'mechanical', 'me', 'automotive engineering', 'thermal engineering'],
        'keywords': ['mechanics', 'thermodynamics', 'design', 'manufacturing']
    },
    'Electrical Engineering': {
        'variations': ['electrical engineering', 'electrical', 'ee', 'power engineering', 'electronics and electrical'],
        'keywords': ['electrical', 'power', 'circuits', 'electronics']
    },
    'Electronics Engineering': {
        'variations': ['electronics engineering', 'electronics', 'electronic', 'ece', 'electronics and communication'],
        'keywords': ['electronics', 'circuits', 'semiconductors', 'embedded']
    },
    'Civil Engineering': {
        'variations': ['civil engineering', 'civil', 'ce', 'construction engineering', 'structural engineering'],
        'keywords': ['construction', 'structural', 'geotechnical', 'transportation']
    },
    'Chemical Engineering': {
        'variations': ['chemical engineering', 'chemical', 'che', 'process engineering', 'petrochemical engineering'],
        'keywords': ['chemical', 'process', 'petrochemical', 'reaction']
    },
    'Aerospace Engineering': {
        'variations': ['aerospace engineering', 'aeronautical engineering', 'astronautical', 'aviation engineering'],
        'keywords': ['aerospace', 'aeronautics', 'spacecraft', 'aviation']
    },
    'Biomedical Engineering': {
        'variations': ['biomedical engineering', 'bme', 'bioengineering', 'medical engineering'],
        'keywords': ['biomedical', 'medical', 'bio', 'healthcare']
    },
    'Environmental Engineering': {
        'variations': ['environmental engineering', 'environmental', 'sustainability engineering', 'ecological engineering'],
        'keywords': ['environment', 'sustainability', 'pollution', 'ecology']
    },
    'Industrial Engineering': {
        'variations': ['industrial engineering', 'industrial', 'ie', 'manufacturing engineering', 'production engineering'],
        'keywords': ['industrial', 'manufacturing', 'production', 'efficiency']
    },
    'Materials Engineering': {
        'variations': ['materials engineering', 'materials science', 'metallurgy', 'polymer engineering'],
        'keywords': ['materials', 'metals', 'polymers', 'composites']
    },
    'Petroleum Engineering': {
        'variations': ['petroleum engineering', 'petroleum', 'oil and gas engineering', 'reservoir engineering'],
        'keywords': ['petroleum', 'oil', 'gas', 'drilling']
    },
    'Mining Engineering': {
        'variations': ['mining engineering', 'mining', 'mine engineering'],
        'keywords': ['mining', 'geology', 'extraction']
    },
    'Marine Engineering': {
        'variations': ['marine engineering', 'naval architecture', 'ocean engineering'],
        'keywords': ['marine', 'ship', 'offshore']
    },
    'Nuclear Engineering': {
        'variations': ['nuclear engineering', 'nuclear', 'nuclear physics'],
        'keywords': ['nuclear', 'atomic', 'energy']
    },
    'Physics': {
        'variations': ['physics', 'applied physics', 'theoretical physics', 'quantum physics'],
        'keywords': ['physics', 'quantum', 'mechanics', 'thermodynamics', 'optics']
    },
    'Chemistry': {
        'variations': ['chemistry', 'organic chemistry', 'inorganic chemistry', 'physical chemistry'],
        'keywords': ['chemistry', 'reaction', 'compounds', 'spectroscopy']
    },
    'Biology': {
        'variations': ['biology', 'molecular biology', 'cellular biology', 'genetics', 'microbiology'],
        'keywords': ['biology', 'dna', 'cells', 'genes', 'evolution']
    },
    'Biotechnology': {
        'variations': ['biotechnology', 'bioengineering', 'genetic engineering', 'bioprocess'],
        'keywords': ['biotech', 'genes', 'fermentation', 'bioprocessing']
    },
    'Biochemistry': {
        'variations': ['biochemistry', 'biochemical', 'molecular biochemistry'],
        'keywords': ['biochemistry', 'proteins', 'enzymes', 'metabolism']
    },
    'Microbiology': {
        'variations': ['microbiology', 'microbial', 'medical microbiology'],
        'keywords': ['microbiology', 'bacteria', 'viruses', 'fungi']
    },
    'Zoology': {
        'variations': ['zoology', 'animal biology', 'wildlife biology'],
        'keywords': ['zoology', 'animals', 'wildlife', 'conservation']
    },
    'Botany': {
        'variations': ['botany', 'plant science', 'plant biology'],
        'keywords': ['botany', 'plants', 'botanical']
    },
    'Ecology': {
        'variations': ['ecology', 'environmental science', 'ecosystem', 'conservation'],
        'keywords': ['ecology', 'ecosystem', 'biodiversity']
    },
    'Geology': {
        'variations': ['geology', 'earth science', 'geoscience', 'earth sciences'],
        'keywords': ['geology', 'earth', 'minerals', 'rock']
    },
    'Oceanography': {
        'variations': ['oceanography', 'marine science', 'oceanology'],
        'keywords': ['ocean', 'marine', 'currents', 'tides']
    },
    'Meteorology': {
        'variations': ['meteorology', 'weather science', 'atmospheric science'],
        'keywords': ['weather', 'climate', 'atmosphere']
    },
    'Astronomy': {
        'variations': ['astronomy', 'astrophysics', 'space science'],
        'keywords': ['astronomy', 'stars', 'planets', 'cosmos']
    },
    'Statistics': {
        'variations': ['statistics', 'statistical', 'biostatistics', 'actuarial science'],
        'keywords': ['statistics', 'probability', 'data analysis', 'regression']
    },
    'Mathematics': {
        'variations': ['mathematics', 'math', 'applied mathematics', 'pure mathematics'],
        'keywords': ['mathematics', 'algebra', 'calculus', 'geometry']
    },
    'Business Administration': {
        'variations': ['business administration', 'business', 'management', 'bba', 'mba', 'business management'],
        'keywords': ['management', 'leadership', 'strategy', 'operations']
    },
    'Finance': {
        'variations': ['finance', 'financial', 'financial management', 'investment', 'banking'],
        'keywords': ['finance', 'investment', 'banking', 'risk', 'portfolio']
    },
    'Marketing': {
        'variations': ['marketing', 'digital marketing', 'branding', 'advertising', 'market research'],
        'keywords': ['marketing', 'brand', 'advertising', 'seo', 'social media']
    },
    'Human Resources': {
        'variations': ['human resources', 'hr', 'personnel management', 'talent management'],
        'keywords': ['hr', 'recruitment', 'training', 'employee relations']
    },
    'Accounting': {
        'variations': ['accounting', 'accountancy', 'financial accounting', 'auditing'],
        'keywords': ['accounting', 'audit', 'tax', 'financial reporting']
    },
    'Economics': {
        'variations': ['economics', 'economy', 'econometrics', 'development economics'],
        'keywords': ['economics', 'trade', 'policy', 'macro', 'micro']
    },
    'International Business': {
        'variations': ['international business', 'global business', 'international trade'],
        'keywords': ['international', 'global', 'trade', 'cross-border']
    },
    'Operations Management': {
        'variations': ['operations management', 'operations', 'supply chain', 'logistics'],
        'keywords': ['operations', 'supply chain', 'logistics', 'inventory']
    },
    'Entrepreneurship': {
        'variations': ['entrepreneurship', 'startup', 'business development', 'venture'],
        'keywords': ['entrepreneurship', 'startup', 'venture', 'innovation']
    },
    'Public Administration': {
        'variations': ['public administration', 'public policy', 'government', 'civil service'],
        'keywords': ['public', 'administration', 'policy', 'government']
    },
    'Hospitality Management': {
        'variations': ['hospitality management', 'hotel management', 'tourism management', 'catering'],
        'keywords': ['hospitality', 'hotel', 'tourism', 'events']
    },
    'Event Management': {
        'variations': ['event management', 'event planning', 'conference management', 'exhibition'],
        'keywords': ['event', 'planning', 'conference', 'wedding']
    },
    'Sports Management': {
        'variations': ['sports management', 'sport management', 'athletic management'],
        'keywords': ['sports', 'athletic', 'coaching']
    },
    'Supply Chain Management': {
        'variations': ['supply chain management', 'logistics', 'operations', 'procurement'],
        'keywords': ['supply chain', 'logistics', 'procurement']
    },
    'Literature': {
        'variations': ['literature', 'english literature', 'comparative literature', 'creative writing'],
        'keywords': ['literature', 'writing', 'poetry', 'novel']
    },
    'History': {
        'variations': ['history', 'ancient history', 'modern history', 'historiography'],
        'keywords': ['history', 'historical', 'civilization']
    },
    'Political Science': {
        'variations': ['political science', 'politics', 'international relations', 'governance'],
        'keywords': ['politics', 'government', 'policy', 'diplomacy']
    },
    'Sociology': {
        'variations': ['sociology', 'social science', 'anthropology', 'urban studies'],
        'keywords': ['sociology', 'social', 'culture', 'society']
    },
    'Psychology': {
        'variations': ['psychology', 'clinical psychology', 'counseling', 'cognitive', 'behavioral'],
        'keywords': ['psychology', 'mental health', 'behavior', 'counseling']
    },
    'Philosophy': {
        'variations': ['philosophy', 'ethics', 'logic', 'metaphysics'],
        'keywords': ['philosophy', 'logic', 'ethics', 'thinking']
    },
    'Anthropology': {
        'variations': ['anthropology', 'social anthropology', 'cultural anthropology'],
        'keywords': ['anthropology', 'culture', 'human evolution']
    },
    'Geography': {
        'variations': ['geography', 'human geography', 'physical geography', 'gis'],
        'keywords': ['geography', 'maps', 'spatial', 'environment']
    },
    'International Relations': {
        'variations': ['international relations', 'ir', 'global affairs', 'diplomacy'],
        'keywords': ['international', 'diplomacy', 'global', 'relations']
    },
    'Linguistics': {
        'variations': ['linguistics', 'language', 'applied linguistics', 'sociolinguistics'],
        'keywords': ['linguistics', 'language', 'grammar']
    },
    'Fine Arts': {
        'variations': ['fine arts', 'visual arts', 'painting', 'sculpture', 'art'],
        'keywords': ['arts', 'painting', 'sculpture', 'visual']
    },
    'Music': {
        'variations': ['music', 'musicology', 'performance', 'composition'],
        'keywords': ['music', 'orchestra', 'instrument', 'composition']
    },
    'Film Studies': {
        'variations': ['film studies', 'cinema', 'film and television', 'media studies'],
        'keywords': ['film', 'cinema', 'directing', 'production']
    },
    'Communication Studies': {
        'variations': ['communication studies', 'mass communication', 'media', 'journalism'],
        'keywords': ['communication', 'media', 'journalism', 'public relations']
    },
    'Journalism': {
        'variations': ['journalism', 'news', 'reporting', 'broadcast journalism', 'digital media'],
        'keywords': ['journalism', 'reporting', 'news', 'media']
    },
    'Public Relations': {
        'variations': ['public relations', 'pr', 'corporate communication', 'crisis communication'],
        'keywords': ['public relations', 'pr', 'media', 'communication']
    },
    'Theatre': {
        'variations': ['theatre', 'drama', 'acting', 'stage performance'],
        'keywords': ['theatre', 'drama', 'acting', 'stage']
    },
    'Education': {
        'variations': ['education', 'teaching', 'pedagogy', 'curriculum', 'instruction'],
        'keywords': ['education', 'teaching', 'pedagogy', 'learning']
    },
    'Medicine': {
        'variations': ['medicine', 'clinical medicine', 'internal medicine', 'surgery', 'mbbs'],
        'keywords': ['medicine', 'clinical', 'patient care', 'diagnosis', 'treatment']
    },
    'Pharmacy': {
        'variations': ['pharmacy', 'pharmaceutical', 'clinical pharmacy', 'pharmacology'],
        'keywords': ['pharmacy', 'drugs', 'medication', 'pharmacology']
    },
    'Nursing': {
        'variations': ['nursing', 'registered nurse', 'rn', 'clinical nursing', 'patient care'],
        'keywords': ['nursing', 'patient care', 'healthcare', 'clinical']
    },
    'Dentistry': {
        'variations': ['dentistry', 'dental', 'dental surgery', 'orthodontics'],
        'keywords': ['dental', 'dentistry', 'oral health']
    },
    'Public Health': {
        'variations': ['public health', 'epidemiology', 'community health', 'health promotion'],
        'keywords': ['public health', 'epidemiology', 'health policy']
    },
    'Physical Therapy': {
        'variations': ['physical therapy', 'physiotherapy', 'rehabilitation', 'kinesiology'],
        'keywords': ['physical therapy', 'rehab', 'movement']
    },
    'Occupational Therapy': {
        'variations': ['occupational therapy', 'occupational', 'rehabilitation'],
        'keywords': ['occupational therapy', 'rehabilitation']
    },
    'Nutrition': {
        'variations': ['nutrition', 'dietetics', 'diet', 'food science', 'nutritional science'],
        'keywords': ['nutrition', 'diet', 'food', 'health']
    },
    'Veterinary Science': {
        'variations': ['veterinary science', 'veterinary medicine', 'veterinary'],
        'keywords': ['veterinary', 'animal health']
    },
    'Forensic Science': {
        'variations': ['forensic science', 'forensics', 'criminalistics'],
        'keywords': ['forensic', 'crime', 'evidence']
    },
    'Law': {
        'variations': ['law', 'legal', 'corporate law', 'criminal law', 'constitutional law'],
        'keywords': ['law', 'legal', 'litigation', 'justice']
    },
    'International Law': {
        'variations': ['international law', 'global law', 'human rights law'],
        'keywords': ['international', 'human rights', 'treaty']
    },
    'Business Law': {
        'variations': ['business law', 'corporate law', 'commercial law'],
        'keywords': ['business', 'corporate', 'legal']
    },
    'Architecture': {
        'variations': ['architecture', 'architectural design', 'building design'],
        'keywords': ['architecture', 'building', 'construction', 'design']
    },
    'Urban Planning': {
        'variations': ['urban planning', 'city planning', 'town planning', 'regional planning'],
        'keywords': ['urban', 'planning', 'city', 'transportation']
    },
    'Interior Design': {
        'variations': ['interior design', 'interior architecture', 'space design'],
        'keywords': ['interior', 'space', 'design', 'decoration']
    },
    'Graphic Design': {
        'variations': ['graphic design', 'visual communication', 'visual design'],
        'keywords': ['graphic', 'visual', 'design', 'illustration']
    },
    'Product Design': {
        'variations': ['product design', 'industrial design', 'design thinking'],
        'keywords': ['product', 'design', 'industrial', 'manufacturing']
    },
    'Fashion Design': {
        'variations': ['fashion design', 'fashion', 'apparel design', 'costume design'],
        'keywords': ['fashion', 'apparel', 'design', 'clothing']
    },
    'UX/UI Design': {
        'variations': ['ux design', 'ui design', 'user experience', 'user interface', 'interaction design'],
        'keywords': ['ux', 'ui', 'user experience', 'interface']
    },
    'Agriculture': {
        'variations': ['agriculture', 'agronomy', 'horticulture', 'animal science', 'crop science'],
        'keywords': ['agriculture', 'farming', 'crop', 'livestock']
    },
    'Food Science': {
        'variations': ['food science', 'food technology', 'food engineering', 'nutrition'],
        'keywords': ['food', 'technology', 'processing', 'quality']
    },
    'Environmental Science': {
        'variations': ['environmental science', 'environmental studies', 'ecology'],
        'keywords': ['environment', 'ecology', 'sustainability']
    },
    'Data Analytics': {
        'variations': ['data analytics', 'business analytics', 'analytics', 'data analysis'],
        'keywords': ['analytics', 'data', 'visualization', 'insights']
    },
    'Business Intelligence': {
        'variations': ['business intelligence', 'bi', 'decision intelligence'],
        'keywords': ['bi', 'intelligence', 'decision', 'dashboards']
    },
    'Risk Management': {
        'variations': ['risk management', 'risk', 'financial risk', 'operational risk'],
        'keywords': ['risk', 'management', 'mitigation']
    },
    'Project Management': {
        'variations': ['project management', 'pm', 'project planning', 'agile', 'scrum'],
        'keywords': ['project', 'management', 'agile', 'scrum']
    },
    'Information Systems': {
        'variations': ['information systems', 'is', 'management information systems', 'mis'],
        'keywords': ['information', 'systems', 'management']
    },
    'Library Science': {
        'variations': ['library science', 'information science', 'library and information science'],
        'keywords': ['library', 'information', 'archival']
    },
    'Sports Science': {
        'variations': ['sports science', 'exercise science', 'kinesiology', 'physical education'],
        'keywords': ['sports', 'exercise', 'kinesiology', 'fitness']
    },
    'Social Work': {
        'variations': ['social work', 'social welfare', 'community development'],
        'keywords': ['social', 'welfare', 'community', 'aid']
    },
    'Criminology': {
        'variations': ['criminology', 'criminal justice', 'forensic psychology'],
        'keywords': ['criminology', 'criminal', 'justice', 'forensic']
    },
}

# 3. JOB CATEGORIES – comprehensive list with variations
JOB_CATEGORIES = {
    # ----- C-Suite & Executive Leadership -----
    'Chief Executive Officer (CEO)': {'variations': ['ceo', 'chief executive officer', 'managing director'], 'keywords': ['executive', 'ceo', 'president']},
    'Chief Operating Officer (COO)': {'variations': ['coo', 'chief operating officer', 'operations director'], 'keywords': ['operations', 'executive', 'coo']},
    'Chief Financial Officer (CFO)': {'variations': ['cfo', 'chief financial officer', 'finance director'], 'keywords': ['finance', 'executive', 'cfo']},
    'Chief Technology Officer (CTO)': {'variations': ['cto', 'chief technology officer', 'technology director'], 'keywords': ['technology', 'executive', 'cto']},
    'Chief Marketing Officer (CMO)': {'variations': ['cmo', 'chief marketing officer', 'marketing director'], 'keywords': ['marketing', 'executive', 'cmo']},
    'Chief Information Officer (CIO)': {'variations': ['cio', 'chief information officer', 'information director'], 'keywords': ['information', 'it', 'executive']},
    'Chief Human Resources Officer (CHRO)': {'variations': ['chro', 'chief human resources officer', 'hr director'], 'keywords': ['hr', 'executive']},
    'Board Member / Director': {'variations': ['board member', 'board director', 'non-executive director'], 'keywords': ['board', 'governance']},
    'General Manager': {'variations': ['general manager', 'gm', 'general manager operations'], 'keywords': ['management', 'operations']},

    # ----- Management & Business Operations -----
    'Operations Manager': {'variations': ['operations manager', 'operational manager', 'ops manager'], 'keywords': ['operations', 'process improvement']},
    'Administrative Services Manager': {'variations': ['administrative services manager', 'office manager', 'facilities manager'], 'keywords': ['administration', 'office']},
    'Facilities Manager': {'variations': ['facilities manager', 'property manager', 'building manager'], 'keywords': ['facilities', 'property']},
    'Project Manager': {'variations': ['project manager', 'pm', 'project lead', 'program manager'], 'keywords': ['project', 'management', 'agile', 'scrum']},
    'Program Manager': {'variations': ['program manager', 'programme manager'], 'keywords': ['program', 'management']},
    'Product Manager': {'variations': ['product manager', 'product owner', 'product lead'], 'keywords': ['product', 'roadmap', 'strategy']},
    'Supply Chain Manager': {'variations': ['supply chain manager', 'logistics manager', 'procurement manager'], 'keywords': ['supply chain', 'logistics', 'procurement']},
    'Logistics Manager': {'variations': ['logistics manager', 'logistics coordinator'], 'keywords': ['logistics', 'supply chain']},
    'Procurement Manager': {'variations': ['procurement manager', 'purchasing manager', 'buyer'], 'keywords': ['procurement', 'purchasing']},
    'Quality Assurance Manager': {'variations': ['qa manager', 'quality manager', 'quality assurance manager'], 'keywords': ['qa', 'quality']},
    'Risk Manager': {'variations': ['risk manager', 'risk analyst', 'operational risk'], 'keywords': ['risk', 'compliance']},
    'Compliance Officer': {'variations': ['compliance officer', 'compliance manager', 'regulatory compliance'], 'keywords': ['compliance', 'regulatory']},
    'Business Development Manager': {'variations': ['business development manager', 'bdm', 'business development lead'], 'keywords': ['business development', 'sales', 'growth']},

    # ----- Finance & Accounting -----
    'Accountant': {'variations': ['accountant', 'chartered accountant', 'cpa', 'auditor', 'financial controller'], 'keywords': ['accounting', 'audit', 'tax']},
    'Financial Analyst': {'variations': ['financial analyst', 'finance analyst', 'investment analyst', 'equity analyst', 'portfolio analyst'], 'keywords': ['finance', 'analysis', 'investment']},
    'Investment Banker': {'variations': ['investment banker', 'ib', 'merger and acquisition'], 'keywords': ['investment banking', 'mergers', 'acquisitions']},
    'Financial Manager': {'variations': ['finance manager', 'financial manager', 'treasury manager', 'risk manager'], 'keywords': ['finance', 'budgeting', 'forecasting']},
    'Audit Manager': {'variations': ['audit manager', 'internal audit', 'audit director'], 'keywords': ['audit', 'compliance', 'internal control']},
    'Tax Consultant': {'variations': ['tax consultant', 'tax advisor', 'tax specialist'], 'keywords': ['tax', 'consulting', 'tax planning']},
    'Actuary': {'variations': ['actuary', 'actuarial analyst', 'actuarial consultant'], 'keywords': ['actuarial', 'risk', 'statistics', 'insurance']},
    'Management Consultant': {'variations': ['management consultant', 'consultant', 'strategy consultant'], 'keywords': ['consulting', 'strategy']},

    # ----- Human Resources -----
    'HR Manager': {'variations': ['hr manager', 'human resources manager', 'talent manager', 'people manager'], 'keywords': ['hr', 'human resources', 'recruitment']},
    'Recruiter': {'variations': ['recruiter', 'talent acquisition', 'headhunter'], 'keywords': ['recruitment', 'hiring', 'talent acquisition']},
    'Training & Development Specialist': {'variations': ['training specialist', 'learning and development', 'l&d'], 'keywords': ['training', 'development', 'learning']},
    'Compensation & Benefits Analyst': {'variations': ['compensation analyst', 'benefits analyst', 'compensation manager'], 'keywords': ['compensation', 'benefits', 'payroll']},

    # ----- Marketing & Communications -----
    'Marketing Manager': {'variations': ['marketing manager', 'brand manager', 'digital marketing manager', 'marketing lead'], 'keywords': ['marketing', 'brand', 'campaign', 'seo']},
    'Brand Manager': {'variations': ['brand manager', 'brand strategist'], 'keywords': ['brand', 'marketing', 'strategy']},
    'Digital Marketing Specialist': {'variations': ['digital marketing specialist', 'seo specialist', 'sem specialist', 'social media manager'], 'keywords': ['digital', 'seo', 'social media', 'adwords']},
    'Social Media Manager': {'variations': ['social media manager', 'social media strategist', 'community manager'], 'keywords': ['social media', 'community', 'digital']},
    'Content Marketing Manager': {'variations': ['content manager', 'content marketing', 'content strategist'], 'keywords': ['content', 'writing', 'strategy', 'blog']},
    'Public Relations Specialist': {'variations': ['pr specialist', 'public relations', 'communications specialist'], 'keywords': ['pr', 'public relations', 'media']},
    'Copywriter': {'variations': ['copywriter', 'content writer', 'technical writer', 'blogger'], 'keywords': ['writing', 'content', 'copywriting']},
    'Market Research Analyst': {'variations': ['market research analyst', 'market researcher'], 'keywords': ['market research', 'analysis']},

    # ----- Sales -----
    'Sales Manager': {'variations': ['sales manager', 'regional sales manager', 'business development manager'], 'keywords': ['sales', 'business development']},
    'Account Manager': {'variations': ['account manager', 'client relationship manager', 'customer success'], 'keywords': ['account', 'client', 'customer success']},
    'Sales Representative': {'variations': ['sales representative', 'sales associate', 'sales executive'], 'keywords': ['sales', 'representative', 'client']},

    # ----- IT & Software (extensive) -----
    'Software Developer': {'variations': ['software developer', 'software engineer', 'programmer', 'coder'], 'keywords': ['software', 'coding', 'development']},
    'Web Developer': {'variations': ['web developer', 'web designer', 'website developer'], 'keywords': ['web', 'html', 'css', 'javascript']},
    'Mobile Developer': {'variations': ['mobile developer', 'android developer', 'ios developer', 'flutter developer', 'react native developer'], 'keywords': ['mobile', 'android', 'ios', 'flutter']},
    'Full Stack Developer': {'variations': ['full stack', 'fullstack', 'full-stack developer', 'full-stack engineer'], 'keywords': ['frontend', 'backend', 'api']},
    'Frontend Developer': {'variations': ['frontend developer', 'front-end developer', 'ui developer'], 'keywords': ['react', 'angular', 'vue', 'html', 'css']},
    'Backend Developer': {'variations': ['backend developer', 'back-end developer', 'api developer', 'microservices developer'], 'keywords': ['node.js', 'python', 'java', 'api']},
    'DevOps Engineer': {'variations': ['devops engineer', 'devops', 'cloud engineer', 'site reliability engineer', 'sre'], 'keywords': ['aws', 'azure', 'docker', 'kubernetes', 'ci/cd']},
    'Data Scientist': {'variations': ['data scientist', 'ai engineer', 'ml engineer', 'machine learning scientist'], 'keywords': ['python', 'r', 'machine learning', 'statistics']},
    'Data Analyst': {'variations': ['data analyst', 'business analyst', 'reporting analyst', 'bi analyst'], 'keywords': ['sql', 'excel', 'tableau', 'power bi']},
    'Machine Learning Engineer': {'variations': ['ml engineer', 'machine learning engineer', 'deep learning engineer', 'ai engineer'], 'keywords': ['tensorflow', 'pytorch', 'keras', 'neural networks']},
    'Data Engineer': {'variations': ['data engineer', 'big data engineer', 'etl developer', 'data pipeline engineer'], 'keywords': ['etl', 'hadoop', 'spark', 'sql']},
    'Database Administrator': {'variations': ['dba', 'database administrator', 'sql admin', 'oracle dba'], 'keywords': ['sql', 'oracle', 'mysql', 'performance']},
    'Systems Administrator': {'variations': ['system administrator', 'sysadmin', 'network admin', 'server admin'], 'keywords': ['linux', 'windows', 'networking', 'security']},
    'Network Engineer': {'variations': ['network engineer', 'network admin', 'cisco engineer'], 'keywords': ['routing', 'switching', 'tcp/ip', 'cisco']},
    'Cloud Architect': {'variations': ['cloud architect', 'aws architect', 'azure architect', 'gcp architect'], 'keywords': ['cloud', 'architecture', 'aws', 'azure']},
    'Cybersecurity Analyst': {'variations': ['cybersecurity analyst', 'security analyst', 'information security analyst', 'cyber analyst'], 'keywords': ['security', 'threat', 'incident response']},
    'Information Security Manager': {'variations': ['information security manager', 'security manager', 'cso'], 'keywords': ['security', 'cybersecurity', 'compliance']},
    'Software Architect': {'variations': ['software architect', 'solution architect', 'technical architect'], 'keywords': ['architecture', 'design patterns', 'microservices']},
    'Technical Lead': {'variations': ['technical lead', 'tech lead', 'engineering lead'], 'keywords': ['lead', 'technical', 'engineering']},
    'QA Engineer': {'variations': ['qa engineer', 'quality assurance', 'test engineer', 'automation tester'], 'keywords': ['testing', 'qa', 'quality', 'automation']},
    'IT Support / Helpdesk': {'variations': ['it support', 'helpdesk', 'desktop support'], 'keywords': ['it', 'support', 'helpdesk', 'troubleshooting']},
    'AI / ML Engineer': {'variations': ['ai engineer', 'ml engineer', 'artificial intelligence engineer'], 'keywords': ['ai', 'machine learning', 'deep learning']},
    'Game Developer': {'variations': ['game developer', 'game programmer', 'game designer'], 'keywords': ['game', 'unity', 'unreal']},
    'Embedded Systems Engineer': {'variations': ['embedded engineer', 'embedded systems engineer', 'firmware engineer', 'iot engineer'], 'keywords': ['embedded', 'firmware', 'iot', 'microcontroller']},
    'Salesforce Developer': {'variations': ['salesforce developer', 'salesforce admin', 'salesforce consultant'], 'keywords': ['salesforce', 'crm', 'apex']},
    'SAP Consultant': {'variations': ['sap consultant', 'sap analyst', 'sap functional consultant'], 'keywords': ['sap', 'erp']},
    'Database Developer': {'variations': ['database developer', 'sql developer', 'pl/sql developer', 'oracle developer'], 'keywords': ['sql', 'oracle', 'mysql', 'postgresql']},

    # ----- Engineering (various disciplines) -----
    'Civil Engineer': {'variations': ['civil engineer', 'structural engineer', 'construction engineer'], 'keywords': ['civil', 'structural', 'construction']},
    'Mechanical Engineer': {'variations': ['mechanical engineer', 'mechanical designer', 'thermal engineer'], 'keywords': ['mechanical', 'design', 'thermodynamics']},
    'Electrical Engineer': {'variations': ['electrical engineer', 'power engineer', 'controls engineer'], 'keywords': ['electrical', 'power', 'circuits']},
    'Electronics Engineer': {'variations': ['electronics engineer', 'electronic engineer', 'embedded hardware engineer'], 'keywords': ['electronics', 'circuits', 'semiconductors']},
    'Chemical Engineer': {'variations': ['chemical engineer', 'process engineer', 'petrochemical engineer'], 'keywords': ['chemical', 'process', 'petrochemical']},
    'Aerospace Engineer': {'variations': ['aerospace engineer', 'aeronautical engineer', 'aviation engineer'], 'keywords': ['aerospace', 'aeronautical', 'aviation']},
    'Biomedical Engineer': {'variations': ['biomedical engineer', 'bioengineer', 'medical device engineer'], 'keywords': ['biomedical', 'medical', 'bio']},
    'Environmental Engineer': {'variations': ['environmental engineer', 'sustainability engineer'], 'keywords': ['environmental', 'sustainability', 'pollution']},
    'Industrial Engineer': {'variations': ['industrial engineer', 'manufacturing engineer', 'production engineer'], 'keywords': ['industrial', 'manufacturing', 'production']},
    'Materials Engineer': {'variations': ['materials engineer', 'metallurgist', 'polymer engineer'], 'keywords': ['materials', 'metals', 'polymers']},
    'Petroleum Engineer': {'variations': ['petroleum engineer', 'oil engineer', 'reservoir engineer'], 'keywords': ['petroleum', 'oil', 'gas']},
    'Mining Engineer': {'variations': ['mining engineer', 'mine engineer'], 'keywords': ['mining', 'extraction', 'geology']},
    'Marine Engineer': {'variations': ['marine engineer', 'naval architect', 'ship engineer'], 'keywords': ['marine', 'naval', 'ship']},
    'Nuclear Engineer': {'variations': ['nuclear engineer', 'nuclear scientist'], 'keywords': ['nuclear', 'radiation', 'energy']},

    # ----- Construction & Trades -----
    'Construction Manager': {'variations': ['construction manager', 'project manager', 'site manager'], 'keywords': ['construction', 'project', 'site']},
    'Electrician': {'variations': ['electrician', 'electrical technician'], 'keywords': ['electrical', 'wiring']},
    'Plumber': {'variations': ['plumber', 'pipefitter'], 'keywords': ['plumbing', 'pipes']},
    'Carpenter': {'variations': ['carpenter', 'joiner', 'cabinet maker'], 'keywords': ['carpentry', 'wood']},
    'Welder': {'variations': ['welder', 'fabricator', 'metal worker'], 'keywords': ['welding', 'metal']},
    'HVAC Technician': {'variations': ['hvac technician', 'hvac engineer', 'refrigeration technician'], 'keywords': ['hvac', 'cooling', 'heating']},

    # ----- Healthcare & Medicine -----
    'Physician': {'variations': ['physician', 'doctor', 'medical doctor', 'md'], 'keywords': ['medicine', 'clinical', 'doctor']},
    'Surgeon': {'variations': ['surgeon', 'surgical specialist', 'orthopedic surgeon'], 'keywords': ['surgery', 'surgeon']},
    'Pharmacist': {'variations': ['pharmacist', 'clinical pharmacist', 'pharmaceutical scientist'], 'keywords': ['pharmacy', 'drugs', 'clinical']},
    'Registered Nurse': {'variations': ['registered nurse', 'rn', 'nurse practitioner', 'clinical nurse'], 'keywords': ['nursing', 'patient care']},
    'Medical Laboratory Technician': {'variations': ['lab technician', 'medical technician', 'clinical lab'], 'keywords': ['lab', 'technician']},
    'Radiologist': {'variations': ['radiologist', 'radiologic technologist', 'x-ray technician'], 'keywords': ['radiology', 'imaging']},
    'Physical Therapist': {'variations': ['physical therapist', 'physiotherapist', 'rehabilitation'], 'keywords': ['physical therapy', 'rehab']},
    'Occupational Therapist': {'variations': ['occupational therapist', 'ot', 'occupational therapy'], 'keywords': ['occupational therapy', 'rehabilitation']},
    'Dentist': {'variations': ['dentist', 'dental surgeon', 'orthodontist'], 'keywords': ['dental', 'dentist']},
    'Veterinarian': {'variations': ['veterinarian', 'vet', 'veterinary doctor'], 'keywords': ['veterinary', 'animal']},
    'Healthcare Administrator': {'variations': ['healthcare administrator', 'hospital administrator', 'clinic manager'], 'keywords': ['healthcare', 'administration']},
    'Public Health Specialist': {'variations': ['public health specialist', 'epidemiologist', 'health educator'], 'keywords': ['public health', 'epidemiology']},
    'Biotech Researcher': {'variations': ['biotech researcher', 'biotechnology scientist', 'research scientist'], 'keywords': ['biotech', 'research']},

    # ----- Law & Legal -----
    'Lawyer': {'variations': ['lawyer', 'attorney', 'legal counsel', 'solicitor', 'advocate'], 'keywords': ['law', 'legal', 'counsel']},
    'Corporate Lawyer': {'variations': ['corporate lawyer', 'corporate counsel', 'in-house lawyer'], 'keywords': ['corporate', 'law']},
    'Criminal Lawyer': {'variations': ['criminal lawyer', 'criminal defense', 'prosecutor'], 'keywords': ['criminal', 'law']},
    'Paralegal': {'variations': ['paralegal', 'legal assistant', 'legal aide'], 'keywords': ['paralegal', 'legal']},
    'Judge': {'variations': ['judge', 'magistrate', 'justice'], 'keywords': ['judge', 'court']},

    # ----- Education & Academics -----
    'University Professor': {'variations': ['professor', 'associate professor', 'assistant professor', 'faculty'], 'keywords': ['professor', 'academic', 'teaching']},
    'School Teacher': {'variations': ['teacher', 'school teacher', 'instructor', 'educator'], 'keywords': ['teaching', 'education', 'school']},
    'Lecturer': {'variations': ['lecturer', 'university lecturer', 'teaching fellow'], 'keywords': ['lecturer', 'teaching', 'university']},
    'School Principal': {'variations': ['principal', 'headmaster', 'school head'], 'keywords': ['principal', 'school', 'administration']},
    'Curriculum Developer': {'variations': ['curriculum developer', 'instructional designer'], 'keywords': ['curriculum', 'instructional design']},
    'Educational Counselor': {'variations': ['counselor', 'guidance counselor', 'school counselor'], 'keywords': ['counseling', 'education']},

    # ----- Science & Research -----
    'Research Scientist': {'variations': ['research scientist', 'researcher', 'research fellow'], 'keywords': ['research', 'science']},
    'Laboratory Manager': {'variations': ['lab manager', 'laboratory supervisor', 'lab director'], 'keywords': ['lab', 'laboratory']},
    'Environmental Scientist': {'variations': ['environmental scientist', 'ecologist', 'conservationist'], 'keywords': ['environmental', 'ecology']},
    'Geologist': {'variations': ['geologist', 'earth scientist', 'geophysicist'], 'keywords': ['geology', 'earth']},
    'Astrophysicist': {'variations': ['astrophysicist', 'astronomer', 'cosmologist'], 'keywords': ['astronomy', 'cosmos']},
    'Chemist': {'variations': ['chemist', 'analytical chemist', 'organic chemist'], 'keywords': ['chemistry']},
    'Biologist': {'variations': ['biologist', 'molecular biologist', 'cell biologist'], 'keywords': ['biology', 'genetics']},
    'Microbiologist': {'variations': ['microbiologist', 'bacteriologist', 'virologist'], 'keywords': ['microbiology']},
    'Statistician': {'variations': ['statistician', 'biostatistician', 'data statistician'], 'keywords': ['statistics', 'data']},

    # ----- Arts, Design, Media -----
    'Graphic Designer': {'variations': ['graphic designer', 'visual designer', 'art director'], 'keywords': ['graphic design', 'visual']},
    'Interior Designer': {'variations': ['interior designer', 'interior architect', 'space planner'], 'keywords': ['interior', 'design']},
    'Fashion Designer': {'variations': ['fashion designer', 'apparel designer', 'costume designer'], 'keywords': ['fashion', 'apparel']},
    'Photographer': {'variations': ['photographer', 'photojournalist', 'commercial photographer'], 'keywords': ['photography', 'images']},
    'Video Editor': {'variations': ['video editor', 'film editor', 'multimedia editor'], 'keywords': ['video', 'editing']},
    'Animator': {'variations': ['animator', '3d animator', 'motion graphics artist'], 'keywords': ['animation', '3d']},
    'Film Director': {'variations': ['film director', 'movie director', 'director'], 'keywords': ['film', 'directing']},
    'Actor': {'variations': ['actor', 'actress', 'performer', 'theatre artist'], 'keywords': ['acting', 'performance']},
    'Musician': {'variations': ['musician', 'composer', 'orchestra musician'], 'keywords': ['music', 'composing']},
    'Journalist': {'variations': ['journalist', 'reporter', 'news anchor', 'correspondent'], 'keywords': ['journalism', 'news']},
    'Editor': {'variations': ['editor', 'copy editor', 'managing editor', 'content editor'], 'keywords': ['editing', 'publication']},
    'Content Writer': {'variations': ['content writer', 'copywriter', 'technical writer', 'blogger'], 'keywords': ['writing', 'content']},

    # ----- Architecture & Urban Planning -----
    'Architect': {'variations': ['architect', 'architectural designer', 'building architect'], 'keywords': ['architecture', 'design']},
    'Urban Planner': {'variations': ['urban planner', 'city planner', 'regional planner'], 'keywords': ['urban planning', 'city']},

    # ----- Hospitality & Tourism -----
    'Hotel Manager': {'variations': ['hotel manager', 'general manager', 'guest services manager'], 'keywords': ['hotel', 'hospitality']},
    'Chef': {'variations': ['chef', 'executive chef', 'sous chef', 'head chef'], 'keywords': ['chef', 'cooking']},
    'Restaurant Manager': {'variations': ['restaurant manager', 'food and beverage manager'], 'keywords': ['restaurant', 'hospitality']},
    'Travel Agent': {'variations': ['travel agent', 'travel consultant', 'tour operator'], 'keywords': ['travel', 'tourism']},
    'Tour Guide': {'variations': ['tour guide', 'tourist guide', 'cultural guide'], 'keywords': ['tourism', 'guide']},

    # ----- Public Service & Social Work -----
    'Social Worker': {'variations': ['social worker', 'case manager', 'community worker'], 'keywords': ['social work', 'community']},
    'Nonprofit Manager': {'variations': ['nonprofit manager', 'ngo manager', 'program manager'], 'keywords': ['nonprofit', 'ngo']},
    'Government Administrator': {'variations': ['government administrator', 'policy analyst', 'civil servant'], 'keywords': ['government', 'public']},
    'Police Officer': {'variations': ['police officer', 'law enforcement'], 'keywords': ['police', 'enforcement']},
    'Firefighter': {'variations': ['firefighter', 'fire rescue'], 'keywords': ['fire', 'rescue']},

    # ----- Agriculture & Natural Resources -----
    'Farmer': {'variations': ['farmer', 'agricultural manager', 'ranch manager'], 'keywords': ['farming', 'agriculture']},
    'Forestry Technician': {'variations': ['forestry technician', 'forester'], 'keywords': ['forestry', 'trees']},
    'Pilot': {'variations': ['pilot', 'airline pilot', 'commercial pilot', 'captain'], 'keywords': ['pilot', 'aviation']},
    'Air Traffic Controller': {'variations': ['air traffic controller', 'atc', 'flight control'], 'keywords': ['air traffic', 'control']},
    'Truck Driver': {'variations': ['truck driver', 'heavy vehicle driver', 'lorry driver'], 'keywords': ['driving', 'logistics']},

    # ----- Customer Service & Support -----
    'Customer Service Representative': {'variations': ['customer service', 'client service', 'support specialist'], 'keywords': ['customer service', 'support']},
    'Receptionist': {'variations': ['receptionist', 'front desk', 'administrative assistant'], 'keywords': ['reception', 'front desk']},
    'Data Entry Clerk': {'variations': ['data entry', 'data operator', 'typist'], 'keywords': ['data entry', 'typing']},
    'Security Guard': {'variations': ['security guard', 'security officer', 'patrol'], 'keywords': ['security', 'guard']},

    # ----- Sales & Services (additional) -----
    'Retail Sales Associate': {'variations': ['retail sales', 'sales associate', 'store associate'], 'keywords': ['retail', 'sales']},
    'Real Estate Agent': {'variations': ['real estate agent', 'realtor', 'real estate broker'], 'keywords': ['real estate', 'property']},
    'Insurance Agent': {'variations': ['insurance agent', 'insurance broker', 'underwriter'], 'keywords': ['insurance', 'underwriting']},

    # ----- Other Professional -----
    'Consultant': {'variations': ['consultant', 'management consultant', 'strategy consultant'], 'keywords': ['consulting', 'advisory']},
    'Entrepreneur': {'variations': ['entrepreneur', 'founder', 'co-founder', 'business owner'], 'keywords': ['entrepreneur', 'startup']},
    'Counselor': {'variations': ['counselor', 'therapist', 'psychotherapist'], 'keywords': ['counseling', 'therapy']},
    'Librarian': {'variations': ['librarian', 'information specialist', 'archivist'], 'keywords': ['library', 'information']},
    'Fitness Trainer': {'variations': ['fitness trainer', 'personal trainer', 'gym instructor'], 'keywords': ['fitness', 'training']},
    'Sports Coach': {'variations': ['sports coach', 'athletic coach', 'fitness trainer'], 'keywords': ['sports', 'coaching']},
}

# ------------------------------
#  EXPERIENCE OPTIONS
# ------------------------------
EXPERIENCE_OPTIONS = [
    "Fresher",
    "1 Year",
    "1+ Years",
    "2+ Years",
    "3+ Years",
    "4+ Years",
    "5+ Years",
    "6+ Years",
    "7+ Years",
    "8+ Years",
    "9+ Years",
    "10+ Years"
]

# ------------------------------
#  HELPER FUNCTIONS
# ------------------------------
candidates_db = []

def normalize_text(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s\+\.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_image(filepath):
    try:
        if not TESSERACT_AVAILABLE:
            return "image file candidate resume"  # fallback
        img = Image.open(filepath)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        text = pytesseract.image_to_string(img)
        return normalize_text(text)
    except Exception as e:
        print(f"OCR Error: {e}")
        return "image file candidate resume"  # fallback

def extract_text(filepath, extension):
    text = ""
    try:
        if extension == "pdf":
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + " "
        elif extension == "docx":
            doc = docx.Document(filepath)
            text = " ".join(p.text for p in doc.paragraphs)
        elif extension in ["jpg", "jpeg", "png", "webp"]:
            return extract_text_from_image(filepath)
    except Exception:
        pass
    return normalize_text(text)

def is_valid_resume(text):
    # Must have reasonable length (at least 100 characters)
    if len(text) < 100:
        return False
    
    # Must contain at least 2 of these common resume terms
    indicators = [
        "experience", "education", "skills", "summary", 
        "employment", "projects", "objective", "qualifications",
        "work", "professional", "certification", "achievement",
        "resume", "cv", "curriculum vitae", "profile"
    ]
    matches = sum(1 for term in indicators if term in text)
    if matches < 2:
        return False
    
    return True

def screen_candidate(resume_text, filters):
    resume_text = normalize_text(resume_text)

    # ----- Must have ALL filters set -----
    has_all_filters = all([
        filters.get("degree", ""),
        filters.get("subject", ""),
        filters.get("job_category", ""),
        filters.get("experience", "Fresher") != "Fresher"
    ])
    
    if not has_all_filters:
        return "Rejected", {}, 0

    # ---- Degree ----
    degree_key = filters.get("degree", "")
    has_degree = False
    if degree_key and degree_key in GENERIC_DEGREES:
        variations = [v.lower() for v in GENERIC_DEGREES[degree_key]['variations']]
        keywords = [k.lower() for k in GENERIC_DEGREES[degree_key]['keywords']]
        variation_match = any(var in resume_text for var in variations)
        keyword_matches = sum(1 for kw in keywords if kw in resume_text)
        has_degree = variation_match or keyword_matches >= 2
    else:
        has_degree = True

    # ---- Subject ----
    subject_key = filters.get("subject", "")
    has_subject = False
    if subject_key and subject_key in SUBJECTS:
        variations = [v.lower() for v in SUBJECTS[subject_key]['variations']]
        keywords = [k.lower() for k in SUBJECTS[subject_key]['keywords']]
        variation_match = any(var in resume_text for var in variations)
        keyword_matches = sum(1 for kw in keywords if kw in resume_text)
        has_subject = variation_match or keyword_matches >= 2
    else:
        has_subject = True

    # ---- Category ----
    category_key = filters.get("job_category", "")
    has_category = False
    if category_key and category_key in JOB_CATEGORIES:
        variations = [v.lower() for v in JOB_CATEGORIES[category_key]['variations']]
        keywords = [k.lower() for k in JOB_CATEGORIES[category_key]['keywords']]
        variation_match = any(var in resume_text for var in variations)
        keyword_matches = sum(1 for kw in keywords if kw in resume_text)
        has_category = variation_match or keyword_matches >= 2
    else:
        has_category = True

    # ---- Experience ----
    exp_filter = filters.get("experience", "Fresher")
    has_experience = False
    if exp_filter == "Fresher":
        has_experience = True
    else:
        match = re.search(r'(\d+(?:\.\d+)?)', exp_filter)
        if match:
            min_years = float(match.group(1))
            years_found = re.findall(r'(\d+)\s*(?:years?|yrs?)', resume_text)
            if years_found:
                max_extracted = max(int(y) for y in years_found)
                has_experience = max_extracted >= min_years
            else:
                plus_pattern = r'(\d+)\s*\+\s*(?:years?|yrs?)'
                match_plus = re.search(plus_pattern, resume_text)
                if match_plus:
                    has_experience = int(match_plus.group(1)) >= min_years

    extracted_info = {
        'degree_found': degree_key if degree_key else 'N/A',
        'subject_found': subject_key if subject_key else 'N/A',
        'category_found': category_key if category_key else 'N/A',
        'experience_years': extract_experience_years(resume_text)
    }

    if all([has_degree, has_subject, has_category, has_experience]):
        return "Accepted", extracted_info, has_experience
    else:
        return "Rejected", extracted_info, has_experience

def extract_experience_years(text):
    """Helper to extract years from resume text."""
    patterns = [
        r'(\d+)\s*\+\s*(?:years?|yrs?)',
        r'(\d+)\s*(?:years?|yrs?)',
        r'experience\s*[:;]\s*(\d+)',
        r'over\s+(\d+)\s*(?:years?|yrs?)'
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return int(m.group(1))
    return 0

# ------------------------------
#  ROUTES
# ------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    # Initialize session filters
    if 'filters' not in session:
        session['filters'] = {
            "degree": "",
            "subject": "",
            "job_category": "",
            "experience": "Fresher"
        }

    if request.method == "POST":
        # Update session filters
        session['filters'] = {
            "degree": request.form.get("degree", ""),
            "subject": request.form.get("subject", ""),
            "job_category": request.form.get("job_category", ""),
            "experience": request.form.get("experience", "Fresher")
        }
        session.modified = True

        files = request.files.getlist("resumes")
        if not files or all(f.filename == "" for f in files):
            flash("⚠️ Upload Error: Please select at least one file.", "error")
            return redirect(request.url)

        user_filters = session['filters']
        processed = 0

        for file in files:
            if not file or file.filename == "":
                continue

            if not allowed_file(file.filename):
                flash(f"⚠️ File format not supported: '{file.filename}'.", "error")
                continue

            ext = file.filename.rsplit(".", 1)[1].lower()
            base_name = secure_filename(file.filename.rsplit(".", 1)[0])
            filename = f"{base_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{get_filter_stats()['total'] + 1}.{ext}"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)

            extracted_text = extract_text(filepath, ext)

            if not is_valid_resume(extracted_text):
                if os.path.exists(filepath):
                    os.remove(filepath)
                flash(f"✗ '{file.filename}' does not appear to be a valid resume or CV.", "error")
                continue

            status, extracted_info, exp_years = screen_candidate(extracted_text, user_filters)
            
            # Save to database
            save_candidate(
                name=base_name.replace("_", " "),
                filename=filename,
                filepath=filepath,
                status=status,
                degree=extracted_info.get('degree_found', 'N/A'),
                subject=extracted_info.get('subject_found', 'N/A'),
                job_category=extracted_info.get('category_found', 'N/A'),
                experience=str(extracted_info.get('experience_years', 0)),
                extracted_text=extracted_text[:5000]  # Store first 5000 chars for search
            )
            
            processed += 1

        if processed:
            flash(f"✓ {processed} resume(s) successfully screened and sorted.", "success")
        return redirect(url_for("index"))

    # GET request – retrieve data from database
    current_filters = session.get('filters', {})
    
    # Get all candidates from database
    all_candidates = get_all_candidates()
    accepted_candidates = [c for c in all_candidates if c['status'] == 'Accepted']
    rejected_candidates = [c for c in all_candidates if c['status'] == 'Rejected']
    stats = get_filter_stats()
    
    # Also get saved filter presets
    filter_presets = get_filter_presets()

    return render_template(
        "index.html",
        total_count=stats['total'],
        accepted_candidates=accepted_candidates,
        rejected_candidates=rejected_candidates,
        degrees=sorted(GENERIC_DEGREES.keys()),
        subjects=sorted(SUBJECTS.keys()),
        categories=sorted(JOB_CATEGORIES.keys()),
        exp_options=EXPERIENCE_OPTIONS,
        filters=current_filters,
        filter_presets=filter_presets
    )

@app.route("/export-all-zip")
def export_all_zip():
    """Export all candidates as a ZIP file organized by status."""
    all_candidates = get_all_candidates()
    
    if not all_candidates:
        flash("No resumes available to export. Please upload and screen some resumes first.", "error")
        return redirect(url_for("index"))
    
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zipf:
        for c in all_candidates:
            file_path = c['filepath']
            if os.path.exists(file_path):
                folder = "Qualified_Candidates" if c['status'] == "Accepted" else "Not_Qualified"
                zip_path = os.path.join(folder, c['filename'])
                zipf.write(file_path, zip_path)
    
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"Screened_Candidates_{datetime.now().strftime('%Y%m%d')}.zip"
    )

@app.route("/view-cv/<filename>")
def view_cv(filename):
    """Serve the resume file for viewing."""
    safe_name = os.path.basename(filename)
    return send_from_directory(app.config["UPLOAD_FOLDER"], safe_name, as_attachment=False)


if __name__ == "__main__":
    # For production, set debug=False and use a proper WSGI server.
    # To run locally with network access, use host='0.0.0.0'
    app.run(debug=False, host='0.0.0.0', port=7860)

# Student Management System

A comprehensive Flask-based web application for managing university student records, courses, enrollments, departments, and instructors.

## Features

- **Student Management**: Add, edit, view, and delete student records with personal information and academic details
- **Course Management**: Manage course offerings, assign instructors, and track enrollments
- **Department Management**: Organize academic departments with faculty assignments
- **Enrollment System**: Track student enrollments with semester and grade information
- **GPA Calculator**: Automatic calculation of student GPA based on course grades
- **Responsive UI**: Clean, intuitive interface built with Bootstrap

## Screenshots

*(Add screenshots of the application here)*

## Tech Stack

- **Backend**: Python, Flask
- **Database**: PostgreSQL
- **Frontend**: HTML, CSS, Bootstrap 5
- **Templating**: Jinja2

## Installation

### Prerequisites

- Python 3.8 or higher
- PostgreSQL 12 or higher
- pip (Python package manager)

### Step 1: Clone the repository

```bash
git clone https://github.com/yourusername/student-management-system.git
cd student-management-system
```

### Step 2: Create a virtual environment

```bash
python -m venv venv
```

### Step 3: Activate the virtual environment

#### On Windows:
```bash
venv\Scripts\activate
```

#### On macOS/Linux:
```bash
source venv/bin/activate
```

### Step 4: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 5: Set up the PostgreSQL database

1. Create a new PostgreSQL database:
```sql
CREATE DATABASE project;
```

2. Update the database connection details in `app/db/__init__.py` if needed:
```python
connection_pool = psycopg2.pool.SimpleConnectionPool(
    1, 20,
    dbname="project",
    user="postgres",
    password="1234",
    host="localhost",
    port="5432"
)
```

3. Run the database initialization script:
```bash
psql -U postgres -d project -f database/init.sql
```

### Step 6: Run the application

```bash
cd app
python app.py
```

The application will be available at `http://localhost:5000`.

## Project Structure

```
app/
├── app.py                # Main Flask application
├── db/
│   └── __init__.py       # Database connection management
├── gpa_calculator.py     # GPA calculation utility
├── models/
│   └── __init__.py       # Model definitions
├── routes/
│   ├── __init__.py       # Route registration
│   ├── courses.py        # Course management routes
│   ├── departments.py    # Department management routes
│   ├── enrollments.py    # Enrollment management routes
│   ├── instructors.py    # Instructor management routes
│   └── students.py       # Student management routes
├── static/
│   ├── css/
│   │   └── style.css     # Custom styles
│   └── js/
│       └── script.js     # JavaScript functions
└── templates/            # HTML templates for all pages
```

## Database Schema

The application uses the following database tables:

- **students**: Student records with personal information
- **departments**: Academic departments
- **instructors**: Faculty members linked to departments
- **courses**: Course information linked to departments and instructors
- **enrollments**: Links students to courses with semester and grade information

## Usage Guidelines

1. **View Database**: Browse existing records without making changes
2. **Manage Database**: Add, edit, or delete records in the database
3. **Students**: Manage student information and view academic progress
4. **Courses**: Create and manage course offerings by semester
5. **Departments**: Organize the academic structure and faculty assignments

## Development

To contribute to this project:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Developed by Jakub Nowicki & Abhijan Poudel
- Built for the Database Management Systems course project

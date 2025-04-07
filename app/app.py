from gpa_calculator import calculate_gpa
from flask import Flask, render_template, flash, redirect, url_for, request, session
import psycopg2
from psycopg2 import pool

app = Flask(__name__)

connection_pool = psycopg2.pool.SimpleConnectionPool(
    1, 20,
    dbname="project",
    user="postgres",
    password="1234",
    host="localhost",
    port="5432"
)

app.secret_key = 'your_secret_key_here'  # Replace with a secure key in production

def get_db_connection():
    return connection_pool.getconn()

def release_db_connection(conn):
    connection_pool.putconn(conn)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/view')
def view():
    return render_template('view.html')

@app.route('/manage')
def manage():
    return render_template('manage.html')


@app.route('/students/manage')
def manage_students():
    return render_template('manage_students.html')


# Add these routes to your app.py file for course management

@app.route('/courses/manage')
def manage_courses():
    return render_template('manage_courses.html')


@app.route('/courses/add', methods=['GET', 'POST'])
def add_course():
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            # Get form data
            course_name = request.form['course_name']
            credits = request.form['credits']
            department_id = request.form['department_id']
            instructor_id = request.form.get('instructor_id', '')  # Optional
            semester = request.form.get('semester', '')  # Optional
            course_id = request.form.get('course_id', '').strip()  # Optional

            # Convert empty strings to None for database
            if not instructor_id:
                instructor_id = None

            cur = conn.cursor()

            # Check if course ID already exists (if provided)
            if course_id:
                cur.execute("SELECT COUNT(*) FROM courses WHERE course_id = %s", (course_id,))
                if cur.fetchone()[0] > 0:
                    # Get departments for dropdown
                    cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
                    departments = cur.fetchall()

                    # Get instructors for dropdown
                    cur.execute("""
                        SELECT i.instructor_id, i.name, i.email, d.department_name 
                        FROM instructors i 
                        JOIN departments d ON i.department_id = d.department_id 
                        ORDER BY i.name
                    """)
                    instructors = cur.fetchall()
                    cur.close()
                    return render_template('add_course.html',
                                           message="Course ID already exists. Please use a different ID or leave blank for auto-generation.",
                                           message_type="danger",
                                           departments=departments,
                                           instructors=instructors)

                # Insert with provided ID
                cur.execute("""
                    INSERT INTO courses (course_id, course_name, credits, department_id, instructor_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (course_id, course_name, credits, department_id, instructor_id))
            else:
                # Find the smallest available ID (this will reuse deleted IDs)
                cur.execute("""
                    SELECT MIN(t.course_id + 1) AS next_id 
                    FROM courses t 
                    WHERE NOT EXISTS (
                        SELECT 1 FROM courses t2 
                        WHERE t2.course_id = t.course_id + 1
                    )
                    UNION
                    SELECT 1
                    WHERE NOT EXISTS (SELECT 1 FROM courses WHERE course_id = 1)
                    ORDER BY next_id
                    LIMIT 1
                """)
                next_id = cur.fetchone()[0]

                if next_id is None:
                    next_id = 1  # Fallback if query returns None

                # Insert with generated ID
                cur.execute("""
                    INSERT INTO courses (course_id, course_name, credits, department_id, instructor_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (next_id, course_name, credits, department_id, instructor_id))
                course_id = next_id

            # Add semester enrollment if specified
            if semester:
                try:
                    # Check if your enrollments table allows NULL student_id
                    # If not, you might need to use a different table or approach
                    cur.execute("""
                        INSERT INTO enrollments (course_id, student_id, semester)
                        VALUES (%s, NULL, %s)
                    """, (course_id, semester))
                except Exception as e:
                    # If this fails, we'll still keep the course but log the error
                    print(f"Warning: Could not add semester offering: {str(e)}")

            conn.commit()
            flash("Course added successfully!", "success")
            return redirect(url_for('edit_course', id=course_id))

        # GET request - show form
        cur = conn.cursor()

        # Get departments for dropdown - only existing departments
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        # Get instructors for dropdown
        cur.execute("""
            SELECT i.instructor_id, i.name, i.email, d.department_name 
            FROM instructors i 
            JOIN departments d ON i.department_id = d.department_id 
            ORDER BY i.name
        """)
        instructors = cur.fetchall()
        cur.close()
        return render_template('add_course.html', departments=departments, instructors=instructors)
    except Exception as e:
        conn.rollback()
        print(f"Error in add_course: {str(e)}")
        flash(f"Error adding course: {str(e)}", "danger")
        return redirect(url_for('manage_courses'))
    finally:
        release_db_connection(conn)


@app.route('/courses/edit')
def edit_courses():
    conn = get_db_connection()
    try:
        search_query = request.args.get('search', '')
        department_filter = request.args.get('department', '')
        page = int(request.args.get('page', 1))
        per_page = 30  # Number of courses per page

        cur = conn.cursor()

        # Get departments for filter dropdown
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        # Base query
        query = """
            SELECT c.course_id, c.course_name, c.credits, c.department_id, c.instructor_id,
                   d.department_name, i.name as instructor_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE 1=1
        """
        params = []

        # Add search condition if search query exists
        if search_query:
            query += " AND (c.course_id::text ILIKE %s OR c.course_name ILIKE %s)"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern])

        # Add department filter if selected
        if department_filter:
            query += " AND c.department_id = %s"
            params.append(department_filter)

        # Add ordering
        query += " ORDER BY c.course_id"

        # Get total count for pagination
        count_query = f"SELECT COUNT(*) FROM ({query}) AS count_query"
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page

        # Add pagination to the query
        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        # Execute final query
        cur.execute(query, params)
        courses = cur.fetchall()

        cur.close()
        return render_template(
            'edit_courses.html',
            courses=courses,
            departments=departments,
            search_query=search_query,
            department_filter=department_filter,
            page=page,
            total_pages=total_pages,
            total_count=total_count
        )
    finally:
        release_db_connection(conn)


@app.route('/courses/edit/<int:id>', methods=['GET'])
def edit_course(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get course details
        cur.execute("""
            SELECT c.course_id, c.course_name, c.credits, c.department_id, c.instructor_id,
                   d.department_name, i.name as instructor_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE c.course_id = %s
        """, (id,))
        course = cur.fetchone()

        if course is None:
            flash("Course not found", "danger")
            return redirect(url_for('edit_courses'))

        # Get enrollment count
        cur.execute("""
            SELECT COUNT(*) FROM enrollments WHERE course_id = %s
        """, (id,))
        enrolled_count = cur.fetchone()[0]

        # Get current semester offerings
        cur.execute("""
            SELECT DISTINCT semester FROM enrollments WHERE course_id = %s
        """, (id,))
        offered_semesters = [row[0] for row in cur.fetchall()]

        # Get current semester (most recent one)
        current_semester = None
        if offered_semesters:
            semester_order = {
                'Fall 2025': 1,
                'Spring 2025': 2,
                'Winter 2025': 3,
                'Fall 2024': 4,
                'Spring 2024': 5,
                'Winter 2024': 6,
                'Fall 2023': 7
            }
            current_semester = min(offered_semesters, key=lambda s: semester_order.get(s, 999))

        # Get enrolled students
        cur.execute("""
            SELECT e.enrollment_id, s.student_id, s.name AS student_name, e.semester, e.grade
            FROM enrollments e
            JOIN students s ON e.student_id = s.student_id
            WHERE e.course_id = %s
            ORDER BY e.semester, s.name
        """, (id,))

        enrolled_students = []
        for row in cur.fetchall():
            enrolled_students.append({
                'enrollment_id': row[0],
                'student_id': row[1],
                'student_name': row[2],
                'semester': row[3],
                'grade': row[4]
            })

        # Get departments for dropdown
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        # Get instructors for dropdown
        cur.execute("""
            SELECT i.instructor_id, i.name, i.email, d.department_name 
            FROM instructors i 
            JOIN departments d ON i.department_id = d.department_id 
            ORDER BY i.name
        """)
        instructors = cur.fetchall()

        # Available semesters
        semesters = ['Fall 2023', 'Winter 2024', 'Spring 2024', 'Fall 2024', 'Winter 2025', 'Spring 2025', 'Fall 2025']

        cur.close()
        return render_template(
            'edit_course.html',
            course=course,
            enrolled_count=enrolled_count,
            enrolled_students=enrolled_students,
            current_semester=current_semester,
            offered_semesters=offered_semesters,
            departments=departments,
            instructors=instructors,
            semesters=semesters
        )
    finally:
        release_db_connection(conn)


@app.route('/courses/update/<int:id>', methods=['POST'])
def update_course(id):
    conn = get_db_connection()
    try:
        course_name = request.form['course_name']
        credits = request.form['credits']
        department_id = request.form['department_id']
        instructor_id = request.form.get('instructor_id', '')

        # Handle empty instructor selection
        if not instructor_id:
            instructor_id = None

        cur = conn.cursor()

        # Update course record
        cur.execute("""
            UPDATE courses
            SET course_name = %s, credits = %s, department_id = %s, instructor_id = %s
            WHERE course_id = %s
        """, (course_name, credits, department_id, instructor_id, id))

        # Handle semester offerings
        selected_semesters = request.form.getlist('semesters[]')

        # Get current semester offerings
        cur.execute("SELECT DISTINCT semester FROM enrollments WHERE course_id = %s", (id,))
        current_semesters = [row[0] for row in cur.fetchall()]

        # Semesters to add
        for semester in selected_semesters:
            if semester not in current_semesters:
                # Check if any students are enrolled for this semester
                cur.execute("""
                    SELECT COUNT(*) FROM enrollments 
                    WHERE course_id = %s AND semester = %s
                """, (id, semester))

                # If no enrollments exist for this semester, create a placeholder enrollment
                if cur.fetchone()[0] == 0:
                    try:
                        cur.execute("""
                            INSERT INTO enrollments (course_id, student_id, semester)
                            VALUES (%s, NULL, %s)
                        """, (id, semester))
                    except Exception as e:
                        print(f"Warning: Could not add semester offering: {str(e)}")

        conn.commit()
        flash("Course updated successfully", "success")
        return redirect(url_for('edit_course', id=id))
    except Exception as e:
        conn.rollback()
        flash(f"Error updating course: {str(e)}", "danger")
        return redirect(url_for('edit_course', id=id))
    finally:
        release_db_connection(conn)


@app.route('/course/<int:id>')
def course_detail(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get course details
        cur.execute("""
            SELECT c.course_id, c.course_name, c.credits, c.department_id, c.instructor_id,
                   d.department_name, i.name as instructor_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE c.course_id = %s
        """, (id,))
        course_data = cur.fetchone()

        if course_data is None:
            flash("Course not found", "danger")
            return redirect(url_for('course_offerings'))

        # Create a dictionary for easier template access
        course = {
            'course_id': course_data[0],
            'course_name': course_data[1],
            'credits': course_data[2],
            'department_id': course_data[3],
            'instructor_id': course_data[4],
            'department_name': course_data[5],
            'instructor_name': course_data[6]
        }

        # Get current semester - Fixed query to avoid ORDER BY with DISTINCT
        cur.execute("""
            SELECT semester FROM (
                SELECT semester,
                       CASE 
                           WHEN semester = 'Fall 2025' THEN 1
                           WHEN semester = 'Spring 2025' THEN 2
                           WHEN semester = 'Winter 2025' THEN 3
                           ELSE 4
                       END AS semester_order
                FROM enrollments 
                WHERE course_id = %s
                GROUP BY semester
            ) AS semesters
            ORDER BY semester_order
            LIMIT 1
        """, (id,))
        semester_row = cur.fetchone()
        course['semester'] = semester_row[0] if semester_row else None

        # Get enrolled students
        cur.execute("""
            SELECT e.enrollment_id, s.student_id, s.name AS student_name, 
                   d.department_name, e.semester, e.grade
            FROM enrollments e
            JOIN students s ON e.student_id = s.student_id
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE e.course_id = %s
            ORDER BY e.semester, s.name
        """, (id,))

        enrolled_students = []
        for row in cur.fetchall():
            enrolled_students.append({
                'enrollment_id': row[0],
                'student_id': row[1],
                'student_name': row[2],
                'department_name': row[3],
                'semester': row[4],
                'grade': row[5]
            })

        cur.close()
        return render_template(
            'course_detail.html',
            course=course,
            enrolled_students=enrolled_students
        )
    except Exception as e:
        print(f"Error in course_detail: {str(e)}")
        flash(f"Error retrieving course details: {str(e)}", "danger")
        return redirect(url_for('course_offerings'))
    finally:
        release_db_connection(conn)

@app.route('/courses/delete/<int:id>', methods=['POST'])
def delete_course(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Delete all enrollments first (due to foreign key constraint)
        cur.execute("DELETE FROM enrollments WHERE course_id = %s", (id,))

        # Delete course record
        cur.execute("DELETE FROM courses WHERE course_id = %s", (id,))

        conn.commit()
        flash("Course deleted successfully", "success")
        return redirect(url_for('edit_courses'))
    except Exception as e:
        conn.rollback()
        flash(f"Error deleting course: {str(e)}", "danger")
        return redirect(url_for('edit_course', id=id))
    finally:
        release_db_connection(conn)

@app.route('/students/edit')
def edit_students():
    conn = get_db_connection()
    try:
        search_query = request.args.get('search', '')
        department_filter = request.args.get('department', '')
        page = int(request.args.get('page', 1))
        per_page = 30  # Updated to 30 students per page as requested

        cur = conn.cursor()

        # Get departments for filter dropdown
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        # Base query
        query = """
            SELECT s.student_id, s.name, s.age, s.email, s.major, d.department_name, s.department_id
            FROM students s
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE 1=1
        """
        params = []

        # Add search condition if search query exists
        if search_query:
            query += " AND (s.student_id::text ILIKE %s OR s.name ILIKE %s)"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern])

        # Add department filter if selected
        if department_filter:
            query += " AND s.department_id = %s"
            params.append(department_filter)

        # Add ordering by student ID instead of name
        query += " ORDER BY s.student_id"

        # Get total count for pagination
        count_query = f"SELECT COUNT(*) FROM ({query}) AS count_query"
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page

        # Add pagination to the query
        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        # Execute final query
        cur.execute(query, params)
        students = cur.fetchall()

        cur.close()
        return render_template(
            'edit_student.html',  # This file exists in your uploads
            students=students,
            departments=departments,
            search_query=search_query,
            department_filter=department_filter,
            page=page,
            total_pages=total_pages,
            total_count=total_count  # Added for "showing X of Y" display
        )
    finally:
        release_db_connection(conn)


@app.route('/students/edit/<int:id>', methods=['GET'])
def edit_student(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get student details
        cur.execute("""
            SELECT s.student_id, s.name, s.age, s.email, s.major, d.department_name, s.department_id
            FROM students s
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE s.student_id = %s
        """, (id,))
        student = cur.fetchone()

        if student is None:
            flash("Student not found", "danger")
            return redirect(url_for('edit_students'))

        # Get student enrollments
        cur.execute("""
            SELECT c.course_name, e.semester, e.grade, i.name as instructor_name
            FROM enrollments e
            JOIN courses c ON e.course_id = c.course_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE e.student_id = %s
            ORDER BY 
                CASE 
                    WHEN e.semester = 'Fall 2025' THEN 1
                    WHEN e.semester = 'Spring 2025' THEN 2
                    WHEN e.semester = 'Winter 2025' THEN 3
                    WHEN e.semester = 'Fall 2024' THEN 4
                    ELSE 5
                END,
                c.course_name
        """, (id,))
        enrollments = cur.fetchall()

        # Get departments for dropdown
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        cur.close()
        return render_template(
            'edit_idnividual.html',  # Use the individual edit template file
            student=student,
            enrollments=enrollments,
            departments=departments
        )
    finally:
        release_db_connection(conn)


# Add these enrollment management routes to your app.py file

@app.route('/students/enrollments/<int:student_id>', methods=['GET'])
def edit_enrollments(student_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get student info
        cur.execute("""
            SELECT s.student_id, s.name, s.email, d.department_name
            FROM students s
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE s.student_id = %s
        """, (student_id,))
        student = cur.fetchone()

        if not student:
            flash("Student not found", "danger")
            return redirect(url_for('edit_students'))

        # Get student enrollments
        cur.execute("""
            SELECT e.enrollment_id, c.course_id, c.course_name, e.semester, e.grade,
                  i.name as instructor_name, d.department_name
            FROM enrollments e
            JOIN courses c ON e.course_id = c.course_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            LEFT JOIN departments d ON c.department_id = d.department_id
            WHERE e.student_id = %s
            ORDER BY 
                CASE 
                    WHEN e.semester = 'Fall 2025' THEN 1
                    WHEN e.semester = 'Spring 2025' THEN 2
                    WHEN e.semester = 'Winter 2025' THEN 3
                    WHEN e.semester = 'Fall 2024' THEN 4
                    ELSE 5
                END,
                c.course_name
        """, (student_id,))
        enrollments = cur.fetchall()

        # Get available courses for adding new enrollments
        cur.execute("""
            SELECT c.course_id, c.course_name, d.department_name, i.name as instructor_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            ORDER BY d.department_name, c.course_name
        """)
        available_courses = cur.fetchall()

        # Get available semesters
        semesters = ['Fall 2023', 'Winter 2024', 'Spring 2024', 'Fall 2024', 'Winter 2025', 'Spring 2025', 'Fall 2025']

        # Get grade options
        grades = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']

        cur.close()
        return render_template(
            'edit_enrollments.html',  # You'll need to create this template
            student=student,
            enrollments=enrollments,
            available_courses=available_courses,
            semesters=semesters,
            grades=grades
        )
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('edit_student', id=student_id))
    finally:
        release_db_connection(conn)


@app.route('/students/enrollment/add/<int:student_id>', methods=['GET', 'POST'])
def add_enrollment(student_id):
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            course_id = request.form['course_id']
            semester = request.form['semester']
            grade = request.form.get('grade', None)
            if grade == '':
                grade = None

            # Check if enrollment already exists
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM enrollments 
                WHERE student_id = %s AND course_id = %s AND semester = %s
            """, (student_id, course_id, semester))

            if cur.fetchone()[0] > 0:
                flash("Enrollment already exists for this student, course, and semester", "danger")
                return redirect(url_for('add_enrollment', student_id=student_id))

            # Add enrollment
            cur.execute("""
                INSERT INTO enrollments (student_id, course_id, semester, grade)
                VALUES (%s, %s, %s, %s)
            """, (student_id, course_id, semester, grade))

            conn.commit()
            flash("Enrollment added successfully", "success")
            return redirect(url_for('edit_enrollments', student_id=student_id))

        # GET request - show form
        cur = conn.cursor()

        # Get student info
        cur.execute("""
            SELECT s.student_id, s.name
            FROM students s
            WHERE s.student_id = %s
        """, (student_id,))
        student = cur.fetchone()

        if not student:
            flash("Student not found", "danger")
            return redirect(url_for('edit_students'))

        # Get available courses
        cur.execute("""
            SELECT c.course_id, c.course_name, d.department_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            ORDER BY d.department_name, c.course_name
        """)
        courses = cur.fetchall()

        # Get available semesters
        semesters = ['Fall 2023', 'Winter 2024', 'Spring 2024', 'Fall 2024', 'Winter 2025', 'Spring 2025', 'Fall 2025']

        # Get grade options
        grades = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']

        cur.close()
        return render_template(
            'add_enrollment.html',  # You'll need to create this template
            student=student,
            courses=courses,
            semesters=semesters,
            grades=grades
        )
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('edit_student', id=student_id))
    finally:
        release_db_connection(conn)


@app.route('/students/enrollment/edit/<int:enrollment_id>', methods=['GET', 'POST'])
def update_enrollment(enrollment_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get enrollment details first (needed for both GET and POST)
        cur.execute("""
            SELECT e.student_id, e.course_id, e.semester, e.grade,
                   s.name as student_name, c.course_name
            FROM enrollments e
            JOIN students s ON e.student_id = s.student_id
            JOIN courses c ON e.course_id = c.course_id
            WHERE e.enrollment_id = %s
        """, (enrollment_id,))
        enrollment = cur.fetchone()

        if not enrollment:
            flash("Enrollment not found", "danger")
            return redirect(url_for('edit_students'))

        student_id = enrollment[0]

        if request.method == 'POST':
            semester = request.form['semester']
            grade = request.form.get('grade', None)
            if grade == '':
                grade = None

            # Update enrollment
            cur.execute("""
                UPDATE enrollments
                SET semester = %s, grade = %s
                WHERE enrollment_id = %s
            """, (semester, grade, enrollment_id))

            conn.commit()
            flash("Enrollment updated successfully", "success")
            return redirect(url_for('edit_enrollments', student_id=student_id))

        # GET request - show form
        # Get available semesters
        semesters = ['Fall 2023', 'Winter 2024', 'Spring 2024', 'Fall 2024', 'Winter 2025', 'Spring 2025', 'Fall 2025']

        # Get grade options
        grades = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']

        cur.close()
        return render_template(
            'edit_enrollment.html',  # You'll need to create this template
            enrollment=enrollment,
            enrollment_id=enrollment_id,
            semesters=semesters,
            grades=grades
        )
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('edit_enrollments', student_id=student_id))
    finally:
        release_db_connection(conn)


@app.route('/students/enrollment/delete/<int:enrollment_id>', methods=['POST'])
def delete_enrollment(enrollment_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get student_id first for redirect
        cur.execute("SELECT student_id FROM enrollments WHERE enrollment_id = %s", (enrollment_id,))
        result = cur.fetchone()

        if not result:
            flash("Enrollment not found", "danger")
            return redirect(url_for('edit_students'))

        student_id = result[0]

        # Delete enrollment
        cur.execute("DELETE FROM enrollments WHERE enrollment_id = %s", (enrollment_id,))

        conn.commit()
        flash("Enrollment deleted successfully", "success")
        return redirect(url_for('edit_enrollments', student_id=student_id))
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('edit_enrollments', student_id=student_id))
    finally:
        release_db_connection(conn)


@app.route('/students/add', methods=['GET', 'POST'])
def add_student():
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            name = request.form['name']
            age = request.form['age']
            email = request.form['email']
            major = request.form['major']
            department_id = request.form['department_id']
            student_id = request.form.get('student_id', '').strip()

            cur = conn.cursor()

            # Check if email already exists
            cur.execute("SELECT COUNT(*) FROM students WHERE email = %s", (email,))
            if cur.fetchone()[0] > 0:
                cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
                departments = cur.fetchall()
                cur.close()
                return render_template('add_student.html',
                                       message="Email already exists in the database.",
                                       message_type="danger",
                                       departments=departments)

            # Insert new student
            if student_id:
                # Check if ID already exists
                cur.execute("SELECT COUNT(*) FROM students WHERE student_id = %s", (student_id,))
                if cur.fetchone()[0] > 0:
                    cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
                    departments = cur.fetchall()
                    cur.close()
                    return render_template('add_student.html',
                                           message="Student ID already exists. Please use a different ID or leave blank for auto-generation.",
                                           message_type="danger",
                                           departments=departments)

                # Insert with provided ID
                cur.execute("""
                    INSERT INTO students (student_id, name, age, email, major, department_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (student_id, name, age, email, major, department_id))
            else:
                # Find the smallest available ID (this will reuse deleted IDs)
                cur.execute("""
                    SELECT MIN(t.student_id + 1) AS next_id 
                    FROM students t 
                    WHERE NOT EXISTS (
                        SELECT 1 FROM students t2 
                        WHERE t2.student_id = t.student_id + 1
                    )
                    UNION
                    SELECT 1
                    WHERE NOT EXISTS (SELECT 1 FROM students WHERE student_id = 1)
                    ORDER BY next_id
                    LIMIT 1
                """)
                next_id = cur.fetchone()[0]

                # Insert student with the next available ID
                cur.execute("""
                    INSERT INTO students (student_id, name, age, email, major, department_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (next_id, name, age, email, major, department_id))
                student_id = next_id

            conn.commit()
            flash("Student added successfully!", "success")
            return redirect(url_for('edit_student', id=student_id))

        # GET request - show form
        cur = conn.cursor()
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()
        cur.close()
        return render_template('add_student.html', departments=departments)
    except Exception as e:
        conn.rollback()
        flash(f"Error adding student: {str(e)}", "danger")
        return redirect(url_for('manage_students'))
    finally:
        release_db_connection(conn)


@app.route('/students/update/<int:id>', methods=['POST'])
def update_student(id):
    conn = get_db_connection()
    try:
        name = request.form['name']
        age = request.form['age']
        email = request.form['email']
        major = request.form['major']
        department_id = request.form['department_id']

        cur = conn.cursor()

        # Check if email already exists for another student
        cur.execute("""
            SELECT COUNT(*) FROM students 
            WHERE email = %s AND student_id != %s
        """, (email, id))

        if cur.fetchone()[0] > 0:
            flash("Email already exists for another student", "danger")
            return redirect(url_for('edit_student', id=id))

        # Update student record
        cur.execute("""
            UPDATE students
            SET name = %s, age = %s, email = %s, major = %s, department_id = %s
            WHERE student_id = %s
        """, (name, age, email, major, department_id, id))

        conn.commit()
        flash("Student updated successfully", "success")
        return redirect(url_for('edit_student', id=id))
    except Exception as e:
        conn.rollback()
        flash(f"Error updating student: {str(e)}", "danger")
        return redirect(url_for('edit_student', id=id))
    finally:
        release_db_connection(conn)


@app.route('/students/delete/<int:id>', methods=['POST'])
def delete_student(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Delete student enrollments first (due to foreign key constraint)
        cur.execute("DELETE FROM enrollments WHERE student_id = %s", (id,))

        # Delete student record
        cur.execute("DELETE FROM students WHERE student_id = %s", (id,))

        conn.commit()
        flash("Student deleted successfully", "success")
        return redirect(url_for('edit_students'))
    except Exception as e:
        conn.rollback()
        flash(f"Error deleting student: {str(e)}", "danger")
        return redirect(url_for('edit_student', id=id))
    finally:
        release_db_connection(conn)


# Add these helper functions
def get_all_departments():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()
        cur.close()
        return departments
    finally:
        release_db_connection(conn)


@app.route('/students')
def list_students():
    conn = get_db_connection()
    try:
        search_query = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = 30  # Students per page

        cur = conn.cursor()

        # Base query
        query = """
            SELECT student_id, name
            FROM students
            WHERE 1=1
        """
        params = []

        # Add search condition if search query exists
        if search_query:
            query += " AND (student_id::text ILIKE %s OR name ILIKE %s)"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern])

        # Add ordering
        query += " ORDER BY student_id"

        # Get total count for pagination
        count_query = f"SELECT COUNT(*) FROM ({query}) AS count_query"
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page

        # Add pagination to the query
        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        # Execute final query
        cur.execute(query, params)
        students = cur.fetchall()

        cur.close()
        return render_template(
            'students.html',
            students=students,
            search_query=search_query,
            page=page,
            total_pages=total_pages,
            total_count=total_count
        )
    finally:
        release_db_connection(conn)

@app.route('/students/<int:id>')
def student_detail(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT s.student_id, s.name, s.age, s.email, s.major, d.department_name
            FROM students s
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE s.student_id = %s
        """, (id,))
        student = cur.fetchone()

        if student is None:
            flash("Student not found", "danger")
            return redirect(url_for('list_students'))

        cur.execute("""
            SELECT c.course_name, c.credits, e.semester, e.grade, i.name as instructor_name
            FROM enrollments e
            JOIN courses c ON e.course_id = c.course_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE e.student_id = %s
            ORDER BY e.semester DESC
        """, (id,))
        all_courses = cur.fetchall()

        current_courses = []
        completed_courses = []
        current_credits = 0

        for course in all_courses:
            credits = course[1] or 0

            if course[3] is None:
                current_courses.append(course)
                current_credits += credits
            else:
                completed_courses.append(course)

        gpa, completed_credits, gpa_points = calculate_gpa(all_courses)

        cur.close()
        return render_template(
            'student_detail.html',
            student=student,
            current_courses=current_courses,
            completed_courses=completed_courses,
            gpa=gpa,
            completed_credits=completed_credits,
            current_credits=current_credits
        )
    finally:
        release_db_connection(conn)

@app.route('/instructors')
def list_instructors():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT i.instructor_id, i.name, i.email, d.department_name
            FROM instructors i
            LEFT JOIN departments d ON i.department_id = d.department_id
            ORDER BY i.name
        """)
        instructors = cur.fetchall()
        cur.close()
        return render_template('instructors_list.html', instructors=instructors)
    finally:
        release_db_connection(conn)

@app.route('/instructors/<int:id>')
def instructor_detail(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT i.instructor_id, i.name, i.email, d.department_name, d.department_id
            FROM instructors i
            LEFT JOIN departments d ON i.department_id = d.department_id
            WHERE i.instructor_id = %s
        """, (id,))
        instructor = cur.fetchone()

        if instructor is None:
            flash("Instructor not found", "danger")
            return redirect(url_for('list_instructors'))

        cur.execute("""
            WITH enrollment_counts AS (
                SELECT course_id, semester, COUNT(*) as enrolled_count
                FROM enrollments
                GROUP BY course_id, semester
            )
            SELECT c.course_id, c.course_name, c.credits, d.department_name, 
                   e.semester, COALESCE(e.enrolled_count, 0) as enrolled_count
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN enrollment_counts e ON c.course_id = e.course_id AND e.semester IS NOT NULL
            WHERE c.instructor_id = %s
            ORDER BY 
                CASE 
                    WHEN e.semester = 'Fall 2025' THEN 1
                    WHEN e.semester = 'Spring 2025' THEN 2
                    WHEN e.semester = 'Winter 2025' THEN 3
                    WHEN e.semester = 'Fall 2024' THEN 4
                    WHEN e.semester = 'Spring 2024' THEN 5
                    WHEN e.semester = 'Winter 2024' THEN 6
                    WHEN e.semester = 'Fall 2023' THEN 7
                    ELSE 8
                END,
                c.course_name
        """, (id,))

        instructor_courses = {}
        for row in cur.fetchall():
            course_info = {
                'course_id': row[0],
                'course_name': row[1],
                'credits': row[2],
                'department_name': row[3],
                'enrolled_count': row[5]
            }

            semester = row[4] or 'Unscheduled'

            if semester not in instructor_courses:
                instructor_courses[semester] = []

            instructor_courses[semester].append(course_info)

        cur.close()
        return render_template(
            'instructors_details.html',
            instructor=instructor,
            instructor_courses=instructor_courses
        )
    finally:
        release_db_connection(conn)

@app.route('/departments')
def list_departments():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT d.department_id, d.department_name, d.head_of_department,
                   COUNT(DISTINCT s.student_id) as student_count,
                   COUNT(DISTINCT c.course_id) as course_count,
                   COUNT(DISTINCT i.instructor_id) as instructor_count
            FROM departments d
            LEFT JOIN students s ON d.department_id = s.department_id
            LEFT JOIN courses c ON d.department_id = c.department_id
            LEFT JOIN instructors i ON d.department_id = i.department_id
            GROUP BY d.department_id, d.department_name, d.head_of_department
            ORDER BY d.department_name
        """)
        departments = cur.fetchall()
        cur.close()
        return render_template('departments_list.html', departments=departments)
    finally:
        release_db_connection(conn)

@app.route('/departments/<int:id>')
def department_detail(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT department_id, department_name, head_of_department
            FROM departments
            WHERE department_id = %s
        """, (id,))
        dept_row = cur.fetchone()

        if dept_row is None:
            flash("Department not found", "danger")
            return redirect(url_for('list_departments'))

        department = {
            'id': dept_row[0],
            'name': dept_row[1],
            'head_of_department': dept_row[2],
            'instructors': [],
            'courses': {},
            'student_count': 0,
            'course_count': 0
        }

        cur.execute("""
            SELECT COUNT(DISTINCT student_id)
            FROM students
            WHERE department_id = %s
        """, (id,))
        department['student_count'] = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(DISTINCT course_id)
            FROM courses
            WHERE department_id = %s
        """, (id,))
        department['course_count'] = cur.fetchone()[0]

        cur.execute("""
            SELECT i.instructor_id, i.name, i.email,
                   COUNT(DISTINCT c.course_id) as course_count
            FROM instructors i
            LEFT JOIN courses c ON i.instructor_id = c.instructor_id
            WHERE i.department_id = %s
            GROUP BY i.instructor_id, i.name, i.email
            ORDER BY i.name
        """, (id,))

        for row in cur.fetchall():
            instructor = {
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'course_count': row[3]
            }
            department['instructors'].append(instructor)

        cur.execute("""
            WITH enrollment_counts AS (
                SELECT course_id, semester, COUNT(*) as enrolled_count
                FROM enrollments
                GROUP BY course_id, semester
            )
            SELECT c.course_id, c.course_name, c.credits, 
                   i.name as instructor_name,
                   e.semester, COALESCE(e.enrolled_count, 0) as enrolled_count
            FROM courses c
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            LEFT JOIN enrollment_counts e ON c.course_id = e.course_id AND e.semester IS NOT NULL
            WHERE c.department_id = %s
            ORDER BY 
                CASE 
                    WHEN e.semester = 'Fall 2025' THEN 1
                    WHEN e.semester = 'Spring 2025' THEN 2
                    WHEN e.semester = 'Winter 2025' THEN 3
                    WHEN e.semester = 'Fall 2024' THEN 4
                    WHEN e.semester = 'Spring 2024' THEN 5
                    WHEN e.semester = 'Winter 2024' THEN 6
                    WHEN e.semester = 'Fall 2023' THEN 7
                    ELSE 8
                END,
                c.course_name
        """, (id,))

        for row in cur.fetchall():
            course_info = {
                'course_id': row[0],
                'course_name': row[1],
                'credits': row[2],
                'instructor_name': row[3],
                'enrolled_count': row[5]
            }

            semester = row[4] or 'Unscheduled'

            if semester not in department['courses']:
                department['courses'][semester] = []

            department['courses'][semester].append(course_info)

        cur.close()
        return render_template(
            'department_details.html',
            department=department
        )
    finally:
        release_db_connection(conn)


@app.route('/course-offerings')
def course_offerings():
    conn = get_db_connection()
    try:
        search_query = request.args.get('search', '')

        cur = conn.cursor()

        # Base query
        query = """
            WITH enrollment_counts AS (
                SELECT course_id, COUNT(*) as enrolled_count
                FROM enrollments
                WHERE semester = 'Fall 2025'
                GROUP BY course_id
            )
            SELECT c.course_id, c.course_name, c.credits, d.department_name, 
                   i.name as instructor_name, COALESCE(e.enrolled_count, 0) as enrolled_count
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            LEFT JOIN enrollment_counts e ON c.course_id = e.course_id
            WHERE 1=1
        """
        params = []

        # Add search condition if search query exists
        if search_query:
            query += " AND (c.course_id::text = %s OR c.course_name ILIKE %s)"
            # For course ID, we want exact matches only
            # For course name, we want partial matches
            params.extend([search_query, f"%{search_query}%"])

        # Add ordering
        query += " ORDER BY d.department_name, c.course_id"

        # Execute query
        cur.execute(query, params)

        current_courses = []
        for row in cur.fetchall():
            current_courses.append({
                'course_id': row[0],
                'course_name': row[1],
                'credits': row[2],
                'department_name': row[3],
                'instructor_name': row[4],
                'enrolled_count': row[5]
            })

        # We skip the historical courses query when searching to keep it focused
        historical_courses = {}
        if not search_query:
            cur.execute("""
                WITH distinct_semesters AS (
                    SELECT DISTINCT course_id, semester
                    FROM enrollments
                    WHERE semester != 'Fall 2025'
                    ORDER BY semester
                )
                SELECT c.course_id, c.course_name, c.credits, d.department_name, 
                       i.name as instructor_name, ds.semester
                FROM distinct_semesters ds
                JOIN courses c ON ds.course_id = c.course_id
                LEFT JOIN departments d ON c.department_id = d.department_id
                LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
                ORDER BY ds.semester DESC, d.department_name, c.course_id
            """)

            semester_to_year = {
                'Fall 2023': '2023-2024',
                'Winter 2024': '2023-2024',
                'Spring 2024': '2023-2024',
                'Fall 2024': '2024-2025',
                'Winter 2025': '2024-2025',
                'Spring 2025': '2024-2025'
            }

            for row in cur.fetchall():
                course_info = {
                    'course_id': row[0],
                    'course_name': row[1],
                    'credits': row[2],
                    'department_name': row[3],
                    'instructor_name': row[4]
                }

                semester = row[5]
                academic_year = semester_to_year.get(semester)

                if academic_year not in historical_courses:
                    historical_courses[academic_year] = {}

                if semester not in historical_courses[academic_year]:
                    historical_courses[academic_year][semester] = []

                historical_courses[academic_year][semester].append(course_info)

            historical_courses = dict(sorted(historical_courses.items(), key=lambda item: item[0], reverse=True))

        cur.close()
        return render_template(
            'course_offerings.html',
            current_courses=current_courses,
            historical_courses=historical_courses,
            search_query=search_query
        )
    finally:
        release_db_connection(conn)


# Add these routes to your app.py file for department management

@app.route('/departments/manage')
def manage_departments():
    return render_template('manage_departments.html')


@app.route('/departments/add', methods=['GET', 'POST'])
def add_department():
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            department_name = request.form['department_name']
            head_of_department = request.form['head_of_department']
            department_id = request.form.get('department_id', '').strip()
            instructor_ids = request.form.getlist('instructors[]')

            cur = conn.cursor()

            # Check if department ID already exists (if provided)
            if department_id:
                cur.execute("SELECT COUNT(*) FROM departments WHERE department_id = %s", (department_id,))
                if cur.fetchone()[0] > 0:
                    cur.execute(
                        "SELECT instructor_id, name, email FROM instructors WHERE department_id IS NULL ORDER BY name")
                    unassigned_instructors = cur.fetchall()
                    cur.close()
                    return render_template('add_department.html',
                                           message="Department ID already exists. Please use a different ID or leave blank for auto-generation.",
                                           message_type="danger",
                                           unassigned_instructors=unassigned_instructors)

                # Insert with provided ID
                cur.execute("""
                    INSERT INTO departments (department_id, department_name, head_of_department)
                    VALUES (%s, %s, %s)
                """, (department_id, department_name, head_of_department))
            else:
                # Auto-generate ID
                cur.execute("""
                    INSERT INTO departments (department_name, head_of_department)
                    VALUES (%s, %s)
                    RETURNING department_id
                """, (department_name, head_of_department))
                department_id = cur.fetchone()[0]

            # Assign instructors to this department if any are selected
            if instructor_ids:
                for instructor_id in instructor_ids:
                    cur.execute("""
                        UPDATE instructors
                        SET department_id = %s
                        WHERE instructor_id = %s
                    """, (department_id, instructor_id))

            conn.commit()
            flash("Department added successfully!", "success")
            return redirect(url_for('edit_department', id=department_id))

        # GET request - show form
        cur = conn.cursor()
        cur.execute("SELECT instructor_id, name, email FROM instructors WHERE department_id IS NULL ORDER BY name")
        unassigned_instructors = cur.fetchall()
        cur.close()
        return render_template('add_department.html', unassigned_instructors=unassigned_instructors)
    except Exception as e:
        conn.rollback()
        flash(f"Error adding department: {str(e)}", "danger")
        return redirect(url_for('manage_departments'))
    finally:
        release_db_connection(conn)


@app.route('/departments/edit')
def edit_departments():
    conn = get_db_connection()
    try:
        search_query = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = 30  # Number of departments per page

        cur = conn.cursor()

        # Base query
        query = """
            SELECT d.department_id, d.department_name, d.head_of_department,
                   COUNT(DISTINCT s.student_id) as student_count,
                   COUNT(DISTINCT c.course_id) as course_count,
                   COUNT(DISTINCT i.instructor_id) as instructor_count
            FROM departments d
            LEFT JOIN students s ON d.department_id = s.department_id
            LEFT JOIN courses c ON d.department_id = c.department_id
            LEFT JOIN instructors i ON d.department_id = i.department_id
        """
        where_clause = []
        params = []

        # Add search condition if search query exists
        if search_query:
            where_clause.append("(d.department_name ILIKE %s OR d.head_of_department ILIKE %s)")
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern])

        if where_clause:
            query += " WHERE " + " AND ".join(where_clause)

        # Add grouping and ordering
        query += " GROUP BY d.department_id, d.department_name, d.head_of_department ORDER BY d.department_name"

        # Get total count for pagination
        count_query = f"SELECT COUNT(*) FROM ({query}) AS count_query"
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page

        # Add pagination to the query
        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        # Execute final query
        cur.execute(query, params)
        departments = cur.fetchall()

        cur.close()
        return render_template(
            'edit_departments.html',
            departments=departments,
            search_query=search_query,
            page=page,
            total_pages=total_pages,
            total_count=total_count
        )
    finally:
        release_db_connection(conn)


@app.route('/departments/edit/<int:id>', methods=['GET'])
def edit_department(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get department details
        cur.execute(
            "SELECT department_id, department_name, head_of_department FROM departments WHERE department_id = %s",
            (id,))
        dept_row = cur.fetchone()

        if dept_row is None:
            flash("Department not found", "danger")
            return redirect(url_for('edit_departments'))

        department = {
            'id': dept_row[0],
            'name': dept_row[1],
            'head_of_department': dept_row[2],
            'instructors': [],
            'courses': {},
            'student_count': 0,
            'course_count': 0,
            'instructor_count': 0
        }

        # Get student count
        cur.execute("SELECT COUNT(*) FROM students WHERE department_id = %s", (id,))
        department['student_count'] = cur.fetchone()[0]

        # Get course count
        cur.execute("SELECT COUNT(*) FROM courses WHERE department_id = %s", (id,))
        department['course_count'] = cur.fetchone()[0]

        # Get instructor count
        cur.execute("SELECT COUNT(*) FROM instructors WHERE department_id = %s", (id,))
        department['instructor_count'] = cur.fetchone()[0]

        # Get instructors in this department
        cur.execute("""
            SELECT i.instructor_id, i.name, i.email,
                   COUNT(DISTINCT c.course_id) as course_count
            FROM instructors i
            LEFT JOIN courses c ON i.instructor_id = c.instructor_id
            WHERE i.department_id = %s
            GROUP BY i.instructor_id, i.name, i.email
            ORDER BY i.name
        """, (id,))

        for row in cur.fetchall():
            instructor = {
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'course_count': row[3]
            }
            department['instructors'].append(instructor)

        # Get available instructors (not assigned to any department)
        cur.execute("SELECT instructor_id, name, email FROM instructors WHERE department_id IS NULL ORDER BY name")
        available_instructors = cur.fetchall()

        # Get courses by semester
        cur.execute("""
            WITH enrollment_counts AS (
                SELECT course_id, semester, COUNT(*) as enrolled_count
                FROM enrollments
                GROUP BY course_id, semester
            )
            SELECT c.course_id, c.course_name, c.credits, 
                   i.name as instructor_name,
                   e.semester, COALESCE(e.enrolled_count, 0) as enrolled_count
            FROM courses c
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            LEFT JOIN enrollment_counts e ON c.course_id = e.course_id AND e.semester IS NOT NULL
            WHERE c.department_id = %s
            ORDER BY 
                CASE 
                    WHEN e.semester = 'Fall 2025' THEN 1
                    WHEN e.semester = 'Spring 2025' THEN 2
                    WHEN e.semester = 'Winter 2025' THEN 3
                    WHEN e.semester = 'Fall 2024' THEN 4
                    WHEN e.semester = 'Spring 2024' THEN 5
                    WHEN e.semester = 'Winter 2024' THEN 6
                    WHEN e.semester = 'Fall 2023' THEN 7
                    ELSE 8
                END,
                c.course_name
        """, (id,))

        for row in cur.fetchall():
            course_info = {
                'course_id': row[0],
                'course_name': row[1],
                'credits': row[2],
                'instructor_name': row[3],
                'enrolled_count': row[5]
            }

            semester = row[4] or 'Unscheduled'

            if semester not in department['courses']:
                department['courses'][semester] = []

            department['courses'][semester].append(course_info)

        cur.close()
        return render_template(
            'edit_department.html',
            department=department,
            available_instructors=available_instructors
        )
    finally:
        release_db_connection(conn)


@app.route('/departments/update/<int:id>', methods=['POST'])
def update_department(id):
    conn = get_db_connection()
    try:
        department_name = request.form['department_name']
        head_of_department = request.form['head_of_department']

        cur = conn.cursor()

        # Update department record
        cur.execute("""
            UPDATE departments
            SET department_name = %s, head_of_department = %s
            WHERE department_id = %s
        """, (department_name, head_of_department, id))

        conn.commit()
        flash("Department updated successfully", "success")
        return redirect(url_for('edit_department', id=id))
    except Exception as e:
        conn.rollback()
        flash(f"Error updating department: {str(e)}", "danger")
        return redirect(url_for('edit_department', id=id))
    finally:
        release_db_connection(conn)


@app.route('/departments/delete/<int:id>', methods=['POST'])
def delete_department(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get the default department (create one if it doesn't exist)
        cur.execute("SELECT department_id FROM departments WHERE department_name = 'General' LIMIT 1")
        default_dept = cur.fetchone()

        if not default_dept:
            cur.execute("""
                INSERT INTO departments (department_name, head_of_department)
                VALUES ('General', 'Administrator')
                RETURNING department_id
            """)
            default_dept_id = cur.fetchone()[0]
        else:
            default_dept_id = default_dept[0]

        # Don't allow deleting the default department
        if id == default_dept_id:
            flash("Cannot delete the default department", "danger")
            return redirect(url_for('edit_departments'))

        # Reassign all students to the default department
        cur.execute("""
            UPDATE students
            SET department_id = %s
            WHERE department_id = %s
        """, (default_dept_id, id))

        # Reassign all courses to the default department
        cur.execute("""
            UPDATE courses
            SET department_id = %s
            WHERE department_id = %s
        """, (default_dept_id, id))

        # Reassign all instructors to the default department
        cur.execute("""
            UPDATE instructors
            SET department_id = %s
            WHERE department_id = %s
        """, (default_dept_id, id))

        # Delete the department
        cur.execute("DELETE FROM departments WHERE department_id = %s", (id,))

        conn.commit()
        flash("Department deleted successfully. All associated records have been reassigned.", "success")
        return redirect(url_for('edit_departments'))
    except Exception as e:
        conn.rollback()
        flash(f"Error deleting department: {str(e)}", "danger")
        return redirect(url_for('edit_department', id=id))
    finally:
        release_db_connection(conn)


@app.route('/departments/<int:dept_id>/add_instructor', methods=['POST'])
def add_instructor_to_department(dept_id):
    conn = get_db_connection()
    try:
        create_new = 'createNew' in request.form

        cur = conn.cursor()

        if create_new:
            # Create a new instructor
            instructor_name = request.form['instructor_name']
            instructor_email = request.form['instructor_email']

            # Check if email already exists
            cur.execute("SELECT COUNT(*) FROM instructors WHERE email = %s", (instructor_email,))
            if cur.fetchone()[0] > 0:
                flash("An instructor with this email already exists", "danger")
                return redirect(url_for('edit_department', id=dept_id))

            # Add the new instructor
            cur.execute("""
                INSERT INTO instructors (name, email, department_id)
                VALUES (%s, %s, %s)
            """, (instructor_name, instructor_email, dept_id))

            flash(f"Instructor '{instructor_name}' created and added to the department", "success")
        else:
            # Add existing instructor to department
            instructor_id = request.form['instructor_id']

            # Update instructor's department
            cur.execute("""
                UPDATE instructors
                SET department_id = %s
                WHERE instructor_id = %s
            """, (dept_id, instructor_id))

            # Get instructor name for the feedback message
            cur.execute("SELECT name FROM instructors WHERE instructor_id = %s", (instructor_id,))
            instructor_name = cur.fetchone()[0]

            flash(f"Instructor '{instructor_name}' added to the department", "success")

        conn.commit()
        return redirect(url_for('edit_department', id=dept_id))
    except Exception as e:
        conn.rollback()
        flash(f"Error adding instructor: {str(e)}", "danger")
        return redirect(url_for('edit_department', id=dept_id))
    finally:
        release_db_connection(conn)


@app.route('/departments/<int:dept_id>/remove_instructor/<int:instructor_id>', methods=['POST'])
def remove_instructor_from_department(dept_id, instructor_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get instructor name for the feedback message
        cur.execute("SELECT name FROM instructors WHERE instructor_id = %s", (instructor_id,))
        instructor_name = cur.fetchone()[0]

        # Remove the instructor's department assignment
        cur.execute("""
            UPDATE instructors
            SET department_id = NULL
            WHERE instructor_id = %s
        """, (instructor_id,))

        conn.commit()
        flash(f"Instructor '{instructor_name}' removed from the department", "success")
        return redirect(url_for('edit_department', id=dept_id))
    except Exception as e:
        conn.rollback()
        flash(f"Error removing instructor: {str(e)}", "danger")
        return redirect(url_for('edit_department', id=dept_id))
    finally:
        release_db_connection(conn)

@app.route('/enrollments')
def list_enrollments():
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                e.enrollment_id,
                s.student_id,
                s.name as student_name,
                c.course_id,
                c.course_name,
                e.semester,
                e.grade,
                i.instructor_id,
                i.name as instructor_name,
                d.department_name
            FROM 
                enrollments e
            JOIN 
                students s ON e.student_id = s.student_id
            JOIN 
                courses c ON e.course_id = c.course_id
            LEFT JOIN 
                instructors i ON c.instructor_id = i.instructor_id
            LEFT JOIN 
                departments d ON c.department_id = d.department_id
            ORDER BY 
                s.student_id,
                CASE 
                    WHEN e.semester = 'Fall 2025' THEN 1
                    WHEN e.semester = 'Spring 2025' THEN 2
                    WHEN e.semester = 'Winter 2025' THEN 3
                    WHEN e.semester = 'Fall 2024' THEN 4
                    WHEN e.semester = 'Spring 2024' THEN 5
                    WHEN e.semester = 'Winter 2024' THEN 6
                    WHEN e.semester = 'Fall 2023' THEN 7
                    ELSE 8
                END,
                c.course_name
        """)

        enrollment_rows = cur.fetchall()
        students_dict = {}

        for row in enrollment_rows:
            student_id = row[1]
            enrollment = {
                'enrollment_id': row[0],
                'course_id': row[3],
                'course_name': row[4],
                'semester': row[5],
                'grade': row[6],
                'instructor_id': row[7],
                'instructor_name': row[8],
                'department_name': row[9]
            }

            if student_id not in students_dict:
                students_dict[student_id] = {
                    'student_id': student_id,
                    'student_name': row[2],
                    'enrollments': [],
                    'total_courses': 0,
                    'current_courses': 0
                }

            students_dict[student_id]['enrollments'].append(enrollment)
            students_dict[student_id]['total_courses'] += 1

            if row[5] == 'Fall 2025':
                students_dict[student_id]['current_courses'] += 1

        students = list(students_dict.values())
        students.sort(key=lambda x: x['student_id'])

        cur.close()
        return render_template('enrollments_list.html', students=students)
    finally:
        release_db_connection(conn)

if __name__ == '__main__':
    app.run(debug=True)
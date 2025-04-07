from flask import Blueprint, render_template, flash, redirect, url_for, request
from db import get_db_connection, release_db_connection

courses_bp = Blueprint('courses', __name__, url_prefix='/courses')


@courses_bp.route('/manage')
def manage_courses():
    return render_template('manage_courses.html')


@courses_bp.route('/add', methods=['GET', 'POST'])
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

            if not instructor_id:
                instructor_id = None

            cur = conn.cursor()

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
            return redirect(url_for('courses.edit_course', id=course_id))

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
        return redirect(url_for('courses.manage_courses'))
    finally:
        release_db_connection(conn)


@courses_bp.route('/edit')
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


@courses_bp.route('/edit/<int:id>', methods=['GET'])
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
            return redirect(url_for('courses.edit_courses'))

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


@courses_bp.route('/update/<int:id>', methods=['POST'])
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
        return redirect(url_for('courses.edit_course', id=id))
    except Exception as e:
        conn.rollback()
        flash(f"Error updating course: {str(e)}", "danger")
        return redirect(url_for('courses.edit_course', id=id))
    finally:
        release_db_connection(conn)


@courses_bp.route('/<int:id>')
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


@courses_bp.route('/delete/<int:id>', methods=['POST'])
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
        return redirect(url_for('courses.edit_courses'))
    except Exception as e:
        conn.rollback()
        flash(f"Error deleting course: {str(e)}", "danger")
        return redirect(url_for('courses.edit_course', id=id))
    finally:
        release_db_connection(conn)


@courses_bp.route('/offerings')
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
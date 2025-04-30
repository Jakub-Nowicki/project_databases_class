from flask import Blueprint, render_template, flash, redirect, url_for, request
from db import get_db_connection, release_db_connection

departments_bp = Blueprint('departments', __name__, url_prefix='/departments')


@departments_bp.route('/')
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


@departments_bp.route('/<int:id>')
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
            return redirect(url_for('departments.list_departments'))

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


@departments_bp.route('/manage')
def manage_departments():
    return render_template('manage_departments.html')


@departments_bp.route('/add', methods=['GET', 'POST'])
def add_department():
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            department_name = request.form['department_name']
            head_of_department = request.form['head_of_department']
            department_id = request.form.get('department_id', '').strip()
            instructor_ids = request.form.getlist('instructors[]')

            cur = conn.cursor()

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

                cur.execute("""
                    INSERT INTO departments (department_id, department_name, head_of_department)
                    VALUES (%s, %s, %s)
                """, (department_id, department_name, head_of_department))
            else:
                cur.execute("""
                    INSERT INTO departments (department_name, head_of_department)
                    VALUES (%s, %s)
                    RETURNING department_id
                """, (department_name, head_of_department))
                department_id = cur.fetchone()[0]

            if instructor_ids:
                for instructor_id in instructor_ids:
                    cur.execute("""
                        UPDATE instructors
                        SET department_id = %s
                        WHERE instructor_id = %s
                    """, (department_id, instructor_id))

            conn.commit()
            flash("Department added successfully!", "success")
            return redirect(url_for('departments.edit_department', id=department_id))

        cur = conn.cursor()
        cur.execute("SELECT instructor_id, name, email FROM instructors WHERE department_id IS NULL ORDER BY name")
        unassigned_instructors = cur.fetchall()
        cur.close()
        return render_template('add_department.html', unassigned_instructors=unassigned_instructors)
    except Exception as e:
        conn.rollback()
        flash(f"Error adding department: {str(e)}", "danger")
        return redirect(url_for('departments.manage_departments'))
    finally:
        release_db_connection(conn)


@departments_bp.route('/edit')
def edit_departments():
    conn = get_db_connection()
    try:
        search_query = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = 30

        cur = conn.cursor()

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

        if search_query:
            where_clause.append("(d.department_name ILIKE %s OR d.head_of_department ILIKE %s)")
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern])

        if where_clause:
            query += " WHERE " + " AND ".join(where_clause)

        query += " GROUP BY d.department_id, d.department_name, d.head_of_department ORDER BY d.department_name"

        count_query = f"SELECT COUNT(*) FROM ({query}) AS count_query"
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page

        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

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


@departments_bp.route('/edit/<int:id>', methods=['GET'])
def edit_department(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT department_id, department_name, head_of_department FROM departments WHERE department_id = %s",
            (id,))
        dept_row = cur.fetchone()

        if dept_row is None:
            flash("Department not found", "danger")
            return redirect(url_for('departments.edit_departments'))

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

        cur.execute("SELECT COUNT(*) FROM students WHERE department_id = %s", (id,))
        department['student_count'] = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM courses WHERE department_id = %s", (id,))
        department['course_count'] = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM instructors WHERE department_id = %s", (id,))
        department['instructor_count'] = cur.fetchone()[0]

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

        cur.execute("SELECT instructor_id, name, email FROM instructors WHERE department_id IS NULL ORDER BY name")
        available_instructors = cur.fetchall()

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


@departments_bp.route('/update/<int:id>', methods=['POST'])
def update_department(id):
    conn = get_db_connection()
    try:
        department_name = request.form['department_name']
        head_of_department = request.form['head_of_department']

        cur = conn.cursor()

        cur.execute("""
            UPDATE departments
            SET department_name = %s, head_of_department = %s
            WHERE department_id = %s
        """, (department_name, head_of_department, id))

        conn.commit()
        flash("Department updated successfully", "success")
        return redirect(url_for('departments.edit_department', id=id))
    except Exception as e:
        conn.rollback()
        flash(f"Error updating department: {str(e)}", "danger")
        return redirect(url_for('departments.edit_department', id=id))
    finally:
        release_db_connection(conn)


@departments_bp.route('/delete/<int:id>', methods=['POST'])
def delete_department(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        print(f"Attempting direct deletion of department ID: {id}")

        # First disable the foreign key constraints temporarily
        cur.execute("SET CONSTRAINTS ALL DEFERRED")

        # Directly delete any references in other tables
        print("Removing related records...")

        # Update students to have NULL department
        cur.execute("UPDATE students SET department_id = NULL WHERE department_id = %s", (id,))
        student_count = cur.rowcount
        print(f"Set {student_count} students to NULL department")

        # Update courses to have NULL department
        cur.execute("UPDATE courses SET department_id = NULL WHERE department_id = %s", (id,))
        course_count = cur.rowcount
        print(f"Set {course_count} courses to NULL department")

        # Update instructors to have NULL department
        cur.execute("UPDATE instructors SET department_id = NULL WHERE department_id = %s", (id,))
        instructor_count = cur.rowcount
        print(f"Set {instructor_count} instructors to NULL department")

        # Now directly delete the department
        cur.execute("DELETE FROM departments WHERE department_id = %s", (id,))
        deleted = cur.rowcount
        print(f"Deleted {deleted} department records")

        conn.commit()
        print("Transaction committed")

        flash("Department successfully deleted", "success")
        return redirect(url_for('departments.edit_departments'))

    except Exception as e:
        conn.rollback()
        print(f"Error in simplified delete_department: {str(e)}")
        flash(f"Error deleting department: {str(e)}", "danger")
        return redirect(url_for('departments.edit_departments'))
    finally:
        release_db_connection(conn)


@departments_bp.route('/<int:dept_id>/add_instructor', methods=['POST'])
def add_instructor_to_department(dept_id):
    conn = get_db_connection()
    try:
        # Debug: Print out all form data to see what's being received
        print("Form data received:", request.form)

        # Check if createNew is in the form data
        create_new = 'createNew' in request.form
        print(f"Create new instructor? {create_new}")

        cur = conn.cursor()

        if create_new:
            print("Attempting to create new instructor")
            # Check if required fields are present
            if 'instructor_name' not in request.form or 'instructor_email' not in request.form:
                print("Missing required fields for new instructor")
                flash("Missing required fields for new instructor", "danger")
                return redirect(url_for('departments.edit_department', id=dept_id))

            instructor_name = request.form['instructor_name']
            instructor_email = request.form['instructor_email']

            print(f"New instructor details: {instructor_name}, {instructor_email}")

            cur.execute("SELECT COUNT(*) FROM instructors WHERE email = %s", (instructor_email,))
            if cur.fetchone()[0] > 0:
                print("Email already exists")
                flash("An instructor with this email already exists", "danger")
                return redirect(url_for('departments.edit_department', id=dept_id))

            # Insert the new instructor - explicitly specify all needed columns
            try:
                cur.execute("""
                    INSERT INTO instructors (name, email, department_id)
                    VALUES (%s, %s, %s)
                    RETURNING instructor_id
                """, (instructor_name, instructor_email, dept_id))

                new_id = cur.fetchone()[0]
                print(f"New instructor created with ID: {new_id}")

                flash(f"Instructor '{instructor_name}' created and added to the department", "success")
            except Exception as e:
                print(f"Database error during insert: {str(e)}")
                raise e

        else:
            # Existing instructor code remains unchanged
            instructor_id = request.form['instructor_id']
            print(f"Adding existing instructor ID: {instructor_id}")

            cur.execute("""
                UPDATE instructors
                SET department_id = %s
                WHERE instructor_id = %s
            """, (dept_id, instructor_id))

            cur.execute("SELECT name FROM instructors WHERE instructor_id = %s", (instructor_id,))
            instructor_name = cur.fetchone()[0]

            flash(f"Instructor '{instructor_name}' added to the department", "success")

        conn.commit()
        return redirect(url_for('departments.edit_department', id=dept_id))
    except Exception as e:
        conn.rollback()
        print(f"Error in add_instructor_to_department: {str(e)}")
        flash(f"Error adding instructor: {str(e)}", "danger")
        return redirect(url_for('departments.edit_department', id=dept_id))
    finally:
        release_db_connection(conn)


@departments_bp.route('/<int:dept_id>/remove_instructor/<int:instructor_id>', methods=['POST'])
def remove_instructor_from_department(dept_id, instructor_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT name FROM instructors WHERE instructor_id = %s", (instructor_id,))
        instructor_name = cur.fetchone()[0]

        cur.execute("""
            UPDATE instructors
            SET department_id = NULL
            WHERE instructor_id = %s
        """, (instructor_id,))

        conn.commit()
        flash(f"Instructor '{instructor_name}' removed from the department", "success")
        return redirect(url_for('departments.edit_department', id=dept_id))
    except Exception as e:
        conn.rollback()
        flash(f"Error removing instructor: {str(e)}", "danger")
        return redirect(url_for('departments.edit_department', id=dept_id))
    finally:
        release_db_connection(conn)

@departments_bp.route('/majors')
def list_majors():
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT d.department_id, d.department_name, s.major, COUNT(*) as student_count
            FROM students s
            JOIN departments d ON s.department_id = d.department_id
            GROUP BY d.department_id, d.department_name, s.major
            ORDER BY d.department_name, s.major
        """)

        departments_majors = {}
        for row in cur.fetchall():
            dept_id = row[0]
            dept_name = row[1]
            major = row[2]
            count = row[3]

            if dept_id not in departments_majors:
                departments_majors[dept_id] = {
                    'name': dept_name,
                    'majors': []
                }

            departments_majors[dept_id]['majors'].append({
                'name': major,
                'student_count': count
            })

        departments_list = []
        for dept_id, dept_data in departments_majors.items():
            departments_list.append({
                'id': dept_id,
                'name': dept_data['name'],
                'majors': sorted(dept_data['majors'], key=lambda x: x['name'])
            })

        departments_list.sort(key=lambda x: x['name'])

        cur.close()
        return render_template('department_majors.html', departments=departments_list)
    finally:
        release_db_connection(conn)
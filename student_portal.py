class Student:
    def __init__(self, roll_no, name):
        self.roll_no = roll_no
        self.name = name
        self.marks_list = []

    def add_marks(self, marks):
        if 0 <= marks <= 100:
            self.marks_list.append(marks)
            print(f"Marks {marks} added successfully.")
        else:
            print("Invalid marks! Enter a value between 0 and 100.")

    def compute_average(self):
        if not self.marks_list:
            return 0.0
        return sum(self.marks_list) / len(self.marks_list)

    def display_details(self):
        avg = self.compute_average()
        print(f"Roll No : {self.roll_no}")
        print(f"Name    : {self.name}")
        print(f"Marks   : {self.marks_list if self.marks_list else 'No marks entered'}")
        print(f"Average : {avg:.2f}")
        print("-" * 40)


# Global list of students
students = []


def add_student():
    roll = input("Enter Roll Number: ").strip()
    # Check if roll number already exists
    for s in students:
        if s.roll_no == roll:
            print("Student with this Roll Number already exists!\n")
            return
    name = input("Enter Student Name: ").strip()
    students.append(Student(roll, name))
    print("Student added successfully!\n")


def enter_marks():
    if not students:
        print("No students available. Please add a student first.\n")
        return
    roll = input("Enter Roll Number: ").strip()
    for s in students:
        if s.roll_no == roll:
            try:
                marks = float(input("Enter marks (0-100): "))
                s.add_marks(marks)
            except ValueError:
                print("Invalid input! Please enter a number.")
            print()
            return
    print("Student not found!\n")


def display_report():
    if not students:
        print("No students in the portal.\n")
        return
    print("\n========== STUDENT REPORT ==========")
    for s in students:
        s.display_details()
    print()


def show_topper():
    if not students:
        print("No students available.\n")
        return

    # Filter students who have at least one mark
    valid_students = [s for s in students if s.marks_list]
    if not valid_students:
        print("No marks entered for any student yet.\n")
        return

    topper = max(valid_students, key=lambda s: s.compute_average())
    print("\n========== TOPPER ==========")
    print(f"Roll No : {topper.roll_no}")
    print(f"Name    : {topper.name}")
    print(f"Average : {topper.compute_average():.2f}")
    print("============================\n")


# Menu-driven program
while True:
    print("===== Simple Student Portal =====")
    print("1. Add Student")
    print("2. Enter Marks")
    print("3. Display Report of All Students")
    print("4. Show Topper")
    print("5. Exit")

    choice = input("Enter your choice (1-5): ")

    if choice == '1':
        add_student()
    elif choice == '2':
        enter_marks()
    elif choice == '3':
        display_report()
    elif choice == '4':
        show_topper()
    elif choice == '5':
        print("Thank you! Exiting Student Portal...")
        break
    else:
        print("Invalid choice. Please try again.\n")
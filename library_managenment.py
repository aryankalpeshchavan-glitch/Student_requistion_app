class Book:
    def __init__(self, title, author, year, available=True):
        self.title = title
        self.author = author
        self.year = year
        self.available = available

    def display(self):
        status = "Available" if self.available else "Issued"
        print(f"{self.title:<30} | {self.author:<20} | {self.year} | {status}")


# Global list of books
library = []


def add_book():
    title = input("Enter book title: ").strip()
    author = input("Enter author name: ").strip()
    year = int(input("Enter publication year: "))
    library.append(Book(title, author, year))
    print("Book added successfully!\n")


def display_all_books():
    if not library:
        print("No books in the library.\n")
        return
    print(f"\n{'Title':<30} | {'Author':<20} | Year | Status")
    print("-" * 70)
    for book in library:
        book.display()
    print()


def search_by_author():
    author = input("Enter author name to search: ").strip().lower()
    found = False
    print(f"\n{'Title':<30} | {'Author':<20} | Year | Status")
    print("-" * 70)
    for book in library:
        if book.author.lower() == author:
            book.display()
            found = True
    if not found:
        print("No books found by this author.")
    print()


def mark_as_issued():
    title = input("Enter book title to mark as issued: ").strip().lower()
    for book in library:
        if book.title.lower() == title:
            if book.available:
                book.available = False
                print(f"'{book.title}' has been marked as issued.\n")
            else:
                print(f"'{book.title}' is already issued.\n")
            return
    print("Book not found.\n")


def mark_as_available():
    title = input("Enter book title to mark as available: ").strip().lower()
    for book in library:
        if book.title.lower() == title:
            if not book.available:
                book.available = True
                print(f"'{book.title}' has been marked as available.\n")
            else:
                print(f"'{book.title}' is already available.\n")
            return
    print("Book not found.\n")


# Menu-driven program
while True:
    print("===== Library Management =====")
    print("1. Add new book")
    print("2. Display all books")
    print("3. Search by author")
    print("4. Mark book as issued")
    print("5. Mark book as available")
    print("6. Exit")
    
    choice = input("Enter your choice (1-6): ")

    if choice == '1':
        add_book()
    elif choice == '2':
        display_all_books()
    elif choice == '3':
        search_by_author()
    elif choice == '4':
        mark_as_issued()
    elif choice == '5':
        mark_as_available()
    elif choice == '6':
        print("Thank you! Exiting...")
        break
    else:
        print("Invalid choice. Please try again.\n")
from io import BytesIO
from threading import RLock


class Book:
    def __init__(
        self,
        title,
        author,
        book_id,
        total_copies,
        image_url=None,
        image_bytes=None,
        image_mime=None,
        price=0.0,
    ):
        total_copies = int(total_copies)
        if total_copies < 0:
            raise ValueError("total_copies cannot be negative")

        self.title = title
        self.author = author
        self.book_id = book_id

        self.total_copies = total_copies
        self.available_copies = total_copies

        self.price = float(price)

        self.image_url = image_url
        self.image_bytes = image_bytes
        self.image_mime = image_mime  # e.g. "image/png"

    def is_available(self):
        return self.available_copies > 0

    def cover_for_streamlit(self):
        if self.image_bytes:
            return BytesIO(self.image_bytes)
        if self.image_url:
            return self.image_url
        return None

    def __str__(self):
        return (
            f"ID: {self.book_id} | {self.title} by {self.author} | "
            f"Total: {self.total_copies} | Available: {self.available_copies}"
        )


class User:
    def __init__(self, name):
        self.name = name
        self.borrowed_books = []

    def borrow(self, book_id):
        self.borrowed_books.append(book_id)

    def return_book(self, book_id):
        if book_id in self.borrowed_books:
            self.borrowed_books.remove(book_id)
            return True
        return False


class Library:
    """
    Streamlit-friendly Library:
    - Thread-safe via RLock.
    - add_book(): existing book -> total_copies SET (overwrite) (avoid double stock on repeated Save).
    - purchase()/restock(): for orders/cart system.
    """

    def __init__(self, name="Digital Library"):
        self.name = name
        self.books = {}
        self.users = {}
        self.borrow_records = []
        self._lock = RLock()

    # -------------------------
    # Basic getters (Streamlit helpers)
    # -------------------------
    def list_book_ids(self):
        with self._lock:
            return list(self.books.keys())

    def get_book(self, book_id):
        with self._lock:
            return self.books.get(book_id)

    def has_book(self, book_id) -> bool:
        with self._lock:
            return book_id in self.books

    # -------------------------
    # Users (borrow/return system)
    # -------------------------
    def get_or_create_user(self, user_name):
        with self._lock:
            if user_name not in self.users:
                self.users[user_name] = User(user_name)
            return self.users[user_name]

    # -------------------------
    # Admin: Add/Update Book
    # -------------------------
    def add_book(
        self,
        title,
        author,
        book_id,
        total_copies,
        image_url=None,
        image_bytes=None,
        image_mime=None,
    ):
        total_copies = int(total_copies)
        if total_copies <= 0:
            return "total_copies must be > 0."

        with self._lock:
            if book_id in self.books:
                b = self.books[book_id]

                # already out (sold/borrowed)
                sold_or_out = b.total_copies - b.available_copies
                if sold_or_out < 0:
                    sold_or_out = 0

                # update meta
                b.title = title
                b.author = author

                # SET total
                b.total_copies = total_copies

                # recompute available safely
                b.available_copies = max(0, b.total_copies - sold_or_out)
                b.available_copies = min(b.total_copies, b.available_copies)

                # cover priority: upload > url > none
                if image_bytes is not None:
                    b.image_bytes = image_bytes
                    b.image_mime = image_mime
                    b.image_url = None
                elif image_url:
                    b.image_url = image_url
                    b.image_bytes = None
                    b.image_mime = None

                return "Book updated (total copies set)."

            self.books[book_id] = Book(
                title=title,
                author=author,
                book_id=book_id,
                total_copies=total_copies,
                image_url=image_url,
                image_bytes=image_bytes,
                image_mime=image_mime,
            )
            return "Book added successfully."

    def set_price(self, book_id, price: float):
        with self._lock:
            if book_id not in self.books:
                return "Book ID not found."
            self.books[book_id].price = float(price)
            return "Price updated."

    def add_stock(self, book_id, qty: int):
        """Extra: increase total + available (use if you want true 'restock' by increasing total)."""
        qty = int(qty)
        if qty <= 0:
            return "qty must be > 0."
        with self._lock:
            if book_id not in self.books:
                return "Book ID not found."
            b = self.books[book_id]
            b.total_copies += qty
            b.available_copies = min(b.total_copies, b.available_copies + qty)
            return "Stock added."

    # -------------------------
    # Selling: purchase/restock (Orders)
    # -------------------------
    def can_purchase(self, items: dict) -> tuple[bool, str]:
        """items: {book_id: qty}"""
        with self._lock:
            for bid, q in items.items():
                q = int(q)
                if bid not in self.books:
                    return False, f"Book ID not found: {bid}"
                if q <= 0:
                    return False, "Qty must be > 0."
                if self.books[bid].available_copies < q:
                    return False, f"Not enough stock for {self.books[bid].title}."
        return True, "OK"

    def purchase(self, items: dict) -> tuple[bool, str]:
        """Atomically reduce stock for an order."""
        ok, msg = self.can_purchase(items)
        if not ok:
            return False, msg

        with self._lock:
            for bid, q in items.items():
                self.books[bid].available_copies -= int(q)
                self.books[bid].available_copies = max(0, self.books[bid].available_copies)
        return True, "Purchased."

    def restock(self, items: dict) -> str:
        """Restock available copies back (never exceeds total_copies)."""
        with self._lock:
            for bid, q in items.items():
                if bid in self.books:
                    b = self.books[bid]
                    b.available_copies = min(b.total_copies, b.available_copies + int(q))
        return "Restocked."

    # -------------------------
    # Borrow/Return (optional)
    # -------------------------
    def borrow_book(self, user_name, book_id):
        with self._lock:
            if book_id not in self.books:
                return "Book ID not found."

            book = self.books[book_id]
            if not book.is_available():
                return "No copies available."

            user = self.get_or_create_user(user_name)
            book.available_copies -= 1
            user.borrow(book_id)

            self.borrow_records.append({"user": user_name, "book_id": book_id, "title": book.title})
            return f"{user_name} borrowed '{book.title}' successfully."

    def return_book(self, user_name, book_id):
        with self._lock:
            if book_id not in self.books:
                return "Book ID not found in library."
            if user_name not in self.users:
                return "User not found."

            user = self.users[user_name]
            if not user.return_book(book_id):
                return "This user did not borrow this book."

            book = self.books[book_id]
            book.available_copies = min(book.total_copies, book.available_copies + 1)

            for i, r in enumerate(self.borrow_records):
                if r["user"] == user_name and r["book_id"] == book_id:
                    self.borrow_records.pop(i)
                    break

            return f"{user_name} returned '{book.title}' successfully."
        # -------------------------
    # Helpers for saving/loading to JSON
    # -------------------------
    def to_dict(self) -> dict:
        """Serialize only books; users/orders app side handle karega."""
        with self._lock:
            return {
                bid: {
                    "title": b.title,
                    "author": b.author,
                    "total_copies": b.total_copies,
                    "available_copies": b.available_copies,
                    "price": getattr(b, "price", 0.0),
                    "image_url": getattr(b, "image_url", None),
                }
                for bid, b in self.books.items()
            }

    def load_from_dict(self, data: dict):
        """JSON se books wapas load karo."""
        with self._lock:
            self.books = {}
            for bid, d in data.items():
                self.books[bid] = Book(
                    title=d["title"],
                    author=d["author"],
                    book_id=bid,
                    total_copies=d["total_copies"],
                    image_url=d.get("image_url"),
                    price=d.get("price", 0.0),
                )
                # available_copies set karo agar saved hai
                self.books[bid].available_copies = d.get(
                    "available_copies", d["total_copies"]
                )

    # -------------------------
    # Search / lists
    # -------------------------
    def search_by_title(self, title):
        t = title.strip().lower()
        with self._lock:
            return [b for b in self.books.values() if t in b.title.lower()]

    def search_by_author(self, author):
        a = author.strip().lower()
        with self._lock:
            return [b for b in self.books.values() if a in b.author.lower()]

    def get_all_books(self):
        with self._lock:
            return list(self.books.values())

    def get_borrow_records(self):
        with self._lock:
            return list(self.borrow_records)

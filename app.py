import streamlit as st
from library_core import Library
from storage import load_state, save_state
from datetime import datetime
from io import BytesIO
from threading import RLock
from streamlit.errors import StreamlitSecretNotFoundError

st.set_page_config(page_title="📚Digital Library", layout="wide")

# -------------------------
# Theme
# -------------------------
def apply_theme(theme_choice: str):
    if theme_choice == "Dark Grey":
        st.markdown(
            """
            <style>
              .stApp { background: #121212; }

              section[data-testid="stSidebar"] {
                  background: #1e1e1e;
                  border-right: 1px solid #333333;
              }

              h1,h2,h3, p, div, span, label {
                  color: #f2f2f2 !important;
              }

              .stTabs [data-baseweb="tab"] {
                  color: #f2f2f2 !important;
              }

              .stTextInput input,
              .stNumberInput input,
              .stSelectbox div[role="combobox"],
              .stTextArea textarea {
                  background: #262626 !important;
                  color: #f2f2f2 !important;
                  border: 1px solid #444444 !important;
              }

              .stDataFrame table {
                  background-color: #181818 !important;
              }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:  # Light Grey
        st.markdown(
            """
            <style>
              .stApp { background: #f0f0f0; }

              section[data-testid="stSidebar"] {
                  background: #e0e0e0;
                  border-right: 1px solid #cccccc;
              }

              h1,h2,h3, p, div, span, label {
                  color: #111111 !important;
              }

              .stTextInput input,
              .stNumberInput input,
              .stSelectbox div[role="combobox"],
              .stTextArea textarea {
                  background: #ffffff !important;
                  color: #111111 !important;
                  border: 1px solid #bbbbbb !important;
              }
            </style>
            """,
            unsafe_allow_html=True,
        )

st.sidebar.header("Theme")
theme_choice = st.sidebar.radio(
    "Theme preset",
    ["Dark Grey", "Light Grey"],
    key="sb_theme",
)
apply_theme(theme_choice)

# -------------------------
# Shared store (global)
# -------------------------
@st.cache_resource
def get_store():
    lib = Library("Digital Library")

    # disk se state load
    state = load_state()
    lib.load_from_dict(state.get("books", {}))
    orders = state.get("orders", [])

    lock = getattr(lib, "_lock", RLock())
    return {"lib": lib, "orders": orders, "lock": lock}

store = get_store()
lib: Library = store["lib"]

# -------------------------
# Session init (per user)
# -------------------------
if "role" not in st.session_state:
    st.session_state.role = None
if "username" not in st.session_state:
    st.session_state.username = ""
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "cart" not in st.session_state:
    st.session_state.cart = {"customer": "", "items": {}}

# -------------------------
# Helpers
# -------------------------
def money_usd(x) -> str:
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "$0.00"

def cover_for_st(book):
    if hasattr(book, "cover_for_streamlit"):
        return book.cover_for_streamlit()
    if getattr(book, "image_bytes", None):
        return BytesIO(book.image_bytes)
    if getattr(book, "image_url", None):
        return book.image_url
    return None

def get_admin_password_default():
    try:
        return st.secrets.get("ADMIN_PASSWORD", "1234")
    except StreamlitSecretNotFoundError:
        return "1234"

def logout():
    st.session_state.role = None
    st.session_state.username = ""
    st.session_state.user_id = ""
    st.session_state.cart = {"customer": "", "items": {}}
    st.rerun()

# ⭐ persist helper
def persist_now():
    """Current books + orders ko JSON file me save karo."""
    with store["lock"]:
        books_dict = lib.to_dict()
        orders_list = list(store["orders"])
    save_state(books_dict, orders_list)

def order_total(items_dict) -> float:
    total = 0.0
    with store["lock"]:
        for bid, q in items_dict.items():
            b = lib.books.get(bid)
            if not b:
                continue
            total += float(getattr(b, "price", 0)) * int(q)
    return total

def items_summary_no_lock(items: dict) -> tuple[str, int]:
    parts = []
    total_qty = 0
    for bid, q in items.items():
        q = int(q)
        b = lib.books.get(bid)
        title = b.title if b else bid
        parts.append(f"{title} x{q}")
        total_qty += q
    return ", ".join(parts), total_qty

def orders_view_rows():
    rows = []
    with store["lock"]:
        for o in store["orders"]:
            summ, qty = items_summary_no_lock(o.get("items", {}))
            rows.append({
                "order_id": o.get("order_id"),
                "time": o.get("time"),
                "customer": o.get("customer"),
                "user_id": o.get("user_id"),
                "items": summ,
                "total_qty": qty,
                "status": o.get("status"),
                "total_usd": o.get("total_usd"),
            })
    return rows

def find_order_index(order_id):
    if not order_id:
        return None
    with store["lock"]:
        for i, o in enumerate(store["orders"]):
            if o.get("order_id") == order_id:
                return i
    return None

def optional_autorefresh(key: str, interval_ms: int = 2000):
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=interval_ms, key=key)
    except Exception:
        pass

def generate_user_id(name: str) -> str:
    """Simple user ID: USR-xxxxx based on current orders length."""
    with store["lock"]:
        n = len(store["orders"]) + 1
    base = name.strip().upper()[:3] or "USR"
    return f"{base}-{n:05d}"

# -------------------------
# Header
# -------------------------
st.markdown("## Digital Library")

# -------------------------
# Login
# -------------------------
if st.session_state.role is None:
    st.subheader("Login")
    role = st.selectbox("Login as", ["User", "Admin"], key="login_role")

    if role == "User":
        name = st.text_input("Your name", placeholder="e.g. Name", key="login_user_name")
        if st.button("Enter as User", type="primary"):
            if not name.strip():
                st.error("Name required.")
            else:
                st.session_state.role = "user"
                st.session_state.username = name.strip()
                st.session_state.user_id = generate_user_id(name.strip())
                st.session_state.cart = {"customer": st.session_state.username, "items": {}}
                st.rerun()
    else:
        admin_pass = st.text_input("Admin password", type="password", key="login_admin_pass")
        if st.button("Enter as Admin", type="primary"):
            if admin_pass == get_admin_password_default():
                st.session_state.role = "admin"
                st.session_state.username = "ADMIN"
                st.session_state.user_id = "ADMIN"
                st.rerun()
            else:
                st.error("Wrong password.")
    st.stop()

# -------------------------
# Top bar
# -------------------------
top_l, top_r = st.columns([3, 1])
with top_l:
    st.caption(
        f"Logged in as: {st.session_state.role.upper()} • "
        f"{st.session_state.username} • ID: {st.session_state.user_id}"
    )
with top_r:
    if st.button("Logout"):
        logout()

# =========================
# ADMIN APP
# =========================
if st.session_state.role == "admin":
    tab_admin_books, tab_admin_inventory, tab_admin_orders = st.tabs(
        ["Admin • Add/Update", "Admin • Inventory", "Admin • Orders"]
    )

    # ---- Add / Update ----
    with tab_admin_books:
        st.subheader("Add / Update Book (Admin)")

        c1, c2, c3 = st.columns(3)
        with c1:
            title = st.text_input("Title", key="adm_title")
        with c2:
            author = st.text_input("Author", key="adm_author")
        with c3:
            book_id = st.text_input("Book ID", key="adm_book_id")

        total_copies = st.number_input("Copies", min_value=1, value=1, step=1, key="adm_copies")
        price = st.number_input("Price (USD)", min_value=0.0, value=0.0, step=1.0, key="adm_price")

        st.markdown("### Cover image")
        cover_mode = st.radio("Choose cover mode", ["Upload", "Image URL", "None"], horizontal=True)

        image_url = None
        image_bytes = None
        image_mime = None

        if cover_mode == "Upload":
            up = st.file_uploader("Upload cover (png/jpg/webp)", type=["png", "jpg", "jpeg", "webp"])
            if up is not None:
                image_bytes = up.getvalue()
                image_mime = up.type
                st.image(BytesIO(image_bytes), caption="Preview", width=240)

        elif cover_mode == "Image URL":
            image_url = st.text_input("Image URL", placeholder="https://.../cover.png")
            if image_url.strip():
                st.image(image_url.strip(), caption="Preview", width=240)

        if st.button("Save Book", type="primary"):
            if not title.strip() or not author.strip() or not book_id.strip():
                st.error("Title, Author, aur Book ID required hain.")
            else:
                with store["lock"]:
                    msg = lib.add_book(
                        title=title.strip(),
                        author=author.strip(),
                        book_id=book_id.strip(),
                        total_copies=int(total_copies),
                        image_url=(image_url.strip() if image_url else None),
                        image_bytes=image_bytes,
                        image_mime=image_mime,
                    )
                    lib.set_price(book_id.strip(), float(price))
                persist_now()
                st.success(msg)
                st.rerun()

    # ---- Inventory ----
    with tab_admin_inventory:
        st.subheader("Inventory (Admin)")
        with store["lock"]:
            books = lib.get_all_books()

        if not books:
            st.info("No books yet.")
        else:
            cols = st.columns(3)
            for i, b in enumerate(books):
                with cols[i % 3]:
                    cover = cover_for_st(b)
                    if cover is not None:
                        st.image(cover, use_container_width=True)
                    st.subheader(b.title)
                    st.write(f"Author: {b.author}")
                    st.write(f"ID: {b.book_id}")
                    st.write(f"Stock: {b.available_copies}/{b.total_copies}")
                    st.write(f"Price: {money_usd(getattr(b, 'price', 0))}")

    # ---- Orders ----
    with tab_admin_orders:
        st.subheader("Orders (Admin)")
        optional_autorefresh(key="adm_orders_refresh", interval_ms=2000)

        rows = orders_view_rows()
        if not rows:
            st.info("No orders yet.")
            st.stop()

        st.dataframe(rows, use_container_width=True)

        st.divider()
        st.subheader("Update / Cancel order")

        order_ids = [r["order_id"] for r in rows]

        sel_id = st.selectbox(
            "Select order",
            order_ids,
            key="adm_order_sel",
            index=None,
            placeholder="Select an order...",
        )

        if sel_id is None:
            st.warning("Please select an order.")
            st.stop()

        idx = find_order_index(str(sel_id))
        if idx is None:
            st.warning("Order not found (refresh).")
            st.stop()

        with store["lock"]:
            o = store["orders"][idx]
            summ, qty = items_summary_no_lock(o.get("items", {}))

        st.write(
            f"Selected: {o.get('order_id')} • {o.get('customer')} "
            f"({o.get('user_id')}) • Qty: {qty} • "
            f"Total {money_usd(o.get('total_usd', 0))}"
        )
        st.write(f"Items: {summ}")
        st.write(f"Status: {o.get('status')}")

        c1, c2, c3 = st.columns(3)
        with c1:
            disabled_deliver = o.get("status") != "PAID"
            if st.button("Mark Delivered", disabled=disabled_deliver):
                with store["lock"]:
                    store["orders"][idx]["status"] = "DELIVERED"
                    persist_now()
                st.rerun()

        # ⭐ Admin -> user ko reminder set karega (admin_note field)
        with c2:
            if st.button("Send payment reminder"):
                with store["lock"]:
                    store["orders"][idx]["admin_note"] = (
                        f"Your order {o.get('order_id')} is still unpaid. "
                        "Kindly confirm your payment."
                    )
                    persist_now()
                st.success("Reminder message has been set for this user.")

        with c3:
            if st.button("Cancel (Restock)"):
                with store["lock"]:
                    items_to_restock = dict(store["orders"][idx].get("items", {}))
                    store["orders"][idx]["status"] = "CANCELLED (RESTOCKED)"
                    lib.restock(items_to_restock)
                    persist_now()
                st.rerun()

# =========================
# USER APP
# =========================
else:
    tab_catalog, tab_buy, tab_my_orders = st.tabs(["Catalog", "Buy", "My Orders"])

    # ---- Catalog ----
    with tab_catalog:
        st.subheader("Catalog")
        with store["lock"]:
            books = lib.get_all_books()

        if not books:
            st.info("No books found. Ask admin to add books.")
        else:
            cols = st.columns(3)
            for i, b in enumerate(books):
                with cols[i % 3]:
                    cover = cover_for_st(b)
                    if cover is not None:
                        st.image(cover, use_container_width=True)
                    st.subheader(b.title)
                    st.write(f"Author: {b.author}")
                    st.write(f"ID: {b.book_id}")
                    st.write(f"Stock: {b.available_copies}")
                    st.write(f"Price: {money_usd(getattr(b, 'price', 0))}")

    # ---- Buy ----
    with tab_buy:
        st.subheader("Buy")
        st.session_state.cart["customer"] = st.session_state.username

        with store["lock"]:
            book_ids = list(lib.books.keys())

        if not book_ids:
            st.info("No books to buy. Ask admin to add books.")
            st.stop()

        def _fmt(bid: str) -> str:
            with store["lock"]:
                b = lib.books.get(bid)
            return f"{bid} • {b.title}" if b else bid

        chosen = st.selectbox("Select book", book_ids, format_func=_fmt)

        with store["lock"]:
            book = lib.books[chosen]

        col1, col2 = st.columns([2, 1])
        with col1:
            cover = cover_for_st(book)
            if cover is not None:
                st.image(cover, width=280)
            st.write(f"Title: {book.title}")
            st.write(f"Stock: {book.available_copies}")
            st.write(f"Price: {money_usd(getattr(book, 'price', 0))}")

        with col2:
            if int(book.available_copies) <= 0:
                st.number_input("Qty", min_value=0, max_value=0, value=0, disabled=True)
                st.button("Add to cart", disabled=True)
                st.warning("Out of stock.")
            else:
                qty = st.number_input(
                    "Qty",
                    min_value=1,
                    max_value=int(book.available_copies),
                    value=1,
                    step=1,
                )
                if st.button("Add to cart"):
                    items = st.session_state.cart["items"]
                    items[book.book_id] = items.get(book.book_id, 0) + int(qty)
                    st.success(f"{st.session_state.username} added {book.title} x{qty} to cart.")
                    st.rerun()

        st.divider()
        st.subheader("Cart")

        items = st.session_state.cart.get("items", {})
        if not items:
            st.write("Cart is empty.")
        else:
            total = order_total(items)

            for bid, q in list(items.items()):
                with store["lock"]:
                    b = lib.books.get(bid)
                if not b:
                    items.pop(bid, None)
                    continue

                line_total = float(getattr(b, "price", 0)) * int(q)
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.write(f"{b.title} (ID: {bid})")
                c2.write(f"Qty: {q}")
                c3.write(money_usd(line_total))
                if c4.button("Remove", key=f"rm_{bid}"):
                    items.pop(bid, None)
                    st.rerun()

            st.write(f"Total: {money_usd(total)}")

            with st.form("confirm_order"):
                submitted = st.form_submit_button("Place Order (Confirm)", type="primary")
                if submitted:
                    customer = st.session_state.username
                    user_id = st.session_state.user_id

                    ok, msg = lib.purchase(items)
                    if not ok:
                        st.error(msg)
                        st.stop()

                    with store["lock"]:
                        order_id = f"ORD-{len(store['orders']) + 1:05d}"
                        store["orders"].append({
                            "order_id": order_id,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "customer": customer,
                            "user_id": user_id,
                            "items": dict(items),
                            "status": "PENDING_PAYMENT",
                            "total_usd": float(total),
                            "admin_note": "",   # ⭐ initially empty
                        })
                        persist_now()

                    st.session_state.cart = {"customer": customer, "items": {}}
                    st.success(f"Order {order_id} created. Please complete payment in 'My Orders'.")
                    st.rerun()

    # ---- My Orders + Payment ----
    with tab_my_orders:
        st.subheader("My Orders & Payment")
        optional_autorefresh(key="usr_orders_refresh", interval_ms=2000)

        all_rows = orders_view_rows()
        my_rows = [r for r in all_rows if r.get("customer") == st.session_state.username]

        if not my_rows:
            st.info("No orders yet.")
        else:
            st.dataframe(my_rows, use_container_width=True)

            for r in my_rows:
                with st.expander(
                    f"{r['order_id']} • {r['status']} • Qty {r['total_qty']} • {money_usd(r['total_usd'])}"
                ):
                    st.write(f"Time: {r['time']}")
                    st.write(f"User ID: {r['user_id']}")
                    st.write(f"Name: {r['customer']}")
                    st.write(f"Items: {r['items']}")
                    st.write(f"Amount to pay: {money_usd(r['total_usd'])}")

                    # ⭐ Admin note show karo agar set hai
                    idx = find_order_index(r["order_id"])
                    if idx is not None:
                        with store["lock"]:
                            note = store["orders"][idx].get("admin_note", "")
                        if note:
                            st.warning(f"Message from admin: {note}")

                    # Fake payment button
                    disabled_pay = r["status"] != "PENDING_PAYMENT"
                    if st.button(
                        f"Pay Now for {r['order_id']}",
                        disabled=disabled_pay,
                        key=f"pay_{r['order_id']}",
                    ):
                        idx = find_order_index(r["order_id"])
                        if idx is not None:
                            with store["lock"]:
                                store["orders"][idx]["status"] = "PAID"
                                persist_now()
                            st.success(f"Payment done for {r['order_id']}.")
                            st.rerun()

"""
Seed mock test suites for Shopee Singapore e-commerce platform.
Run from app/ directory: python3 seed_test_suites.py

Uses sqlite3 directly so it works without sqlalchemy in sandbox.
"""
import sqlite3
import json
import uuid
from datetime import datetime, timedelta
import random

DB_PATH = "web/de_team.db"

# Agent IDs from the existing seeded agents
AGENTS = {
    "promotion": ("c066288e-4773-44a5-940e-191d1453c97c", "Alice · Promo QA"),
    "checkout":  ("d32b2587-0eb1-4b6d-87a1-e880e6a0bef9", "Bob · Checkout QA"),
    "payment":   ("bee2b2f1-aac5-488c-96f7-32217fd13c7d", "Carol · Payment QA"),
}

# Use checkout agent as fallback for logistics / search suites
FALLBACK_AGENT = AGENTS["checkout"]

NOW = datetime.utcnow()

def ts(offset_days=0):
    return (NOW - timedelta(days=offset_days)).strftime("%Y-%m-%d %H:%M:%S")

SUITES = [
    # ── Checkout ──────────────────────────────────────────────────────────────
    {
        "name": "Checkout — Order Placement Happy Path",
        "description": "End-to-end checkout flow covering standard single-seller and multi-seller orders on Shopee SG.",
        "component": "Checkout",
        "source_type": "jira",
        "jira_key": "SPCH-1001",
        "agent": AGENTS["checkout"],
        "created_offset": 5,
        "cases": [
            {
                "title": "Place order with single item — ShopeePay",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "User is logged in; cart has 1 in-stock item; ShopeePay balance ≥ item price",
                "steps": [
                    "Navigate to product page and tap 'Buy Now'",
                    "Confirm default delivery address on checkout page",
                    "Select ShopeePay as payment method",
                    "Tap 'Place Order'",
                    "Verify OTP if prompted",
                ],
                "expected": "Order is created with status 'To Ship'; ShopeePay balance is deducted; order confirmation email sent within 1 min.",
            },
            {
                "title": "Place multi-seller order with free shipping voucher",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "Cart has items from 2 different sellers; user holds a valid platform free-shipping voucher",
                "steps": [
                    "Go to cart, verify items from 2 sellers are split into separate shipment groups",
                    "Apply platform free-shipping voucher in 'Vouchers' section",
                    "Verify shipping fee becomes SGD 0 for eligible shipments",
                    "Select credit card and complete 3DS verification",
                    "Confirm order placement",
                ],
                "expected": "Two separate sub-orders created (one per seller); shipping fee waived; order total matches item subtotals.",
            },
            {
                "title": "Checkout with delivery address change mid-flow",
                "category": "Happy Path",
                "priority": "P1",
                "preconditions": "User has at least 2 saved delivery addresses",
                "steps": [
                    "Begin checkout from cart",
                    "Tap 'Change' on delivery address",
                    "Select a different saved address",
                    "Verify delivery fee recalculates for new address zone",
                    "Complete payment",
                ],
                "expected": "Order saved with updated address; delivery fee reflects correct zone pricing.",
            },
            {
                "title": "Apply seller voucher and verify discount",
                "category": "Happy Path",
                "priority": "P1",
                "preconditions": "Item in cart belongs to a seller who has issued a 10% discount voucher; user holds the voucher",
                "steps": [
                    "Open checkout page",
                    "Tap 'Add Voucher' under the seller group",
                    "Enter seller voucher code and apply",
                    "Verify order total reflects 10% discount on seller items",
                ],
                "expected": "Discount applied correctly; voucher deducted once from seller subtotal; total is accurate.",
            },
            {
                "title": "Checkout with Shopee Coins offset",
                "category": "Happy Path",
                "priority": "P2",
                "preconditions": "User has ≥ 100 Shopee Coins; order total ≥ SGD 5",
                "steps": [
                    "On checkout page, toggle 'Use Shopee Coins'",
                    "Verify maximum coin deduction shown (≤ 10% of order value per platform rule)",
                    "Complete payment with remaining balance via ShopeePay",
                ],
                "expected": "Coins deducted up to the allowed cap; order total reduced accordingly; coins balance updated post-order.",
            },
        ],
    },
    {
        "name": "Checkout — Cart Management",
        "description": "Test cases covering add-to-cart, quantity changes, item removal, and cart persistence on Shopee SG.",
        "component": "Checkout",
        "source_type": "manual",
        "agent": AGENTS["checkout"],
        "created_offset": 12,
        "cases": [
            {
                "title": "Add in-stock item to cart",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "User is logged in; product is in stock",
                "steps": [
                    "Open product detail page",
                    "Select variant (colour/size) if applicable",
                    "Tap 'Add to Cart'",
                ],
                "expected": "Cart icon badge increments by 1; item appears in cart with correct variant, quantity=1, and price.",
            },
            {
                "title": "Increase item quantity beyond stock limit",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "Item in cart has stock=3; cart already has quantity=3",
                "steps": [
                    "On cart page, tap '+' to increase quantity to 4",
                ],
                "expected": "System caps quantity at 3; toast shows 'Insufficient stock'; quantity does not exceed available stock.",
            },
            {
                "title": "Remove item from cart",
                "category": "Happy Path",
                "priority": "P1",
                "preconditions": "Cart has at least 2 items",
                "steps": [
                    "Long-press item in cart or tap delete icon",
                    "Confirm deletion on dialog",
                ],
                "expected": "Item removed from cart; cart total updates immediately; badge count decrements.",
            },
            {
                "title": "Cart persists across sessions",
                "category": "Regression",
                "priority": "P1",
                "preconditions": "User adds 2 items to cart then logs out",
                "steps": [
                    "Log out of app",
                    "Log back in with same account",
                    "Navigate to cart",
                ],
                "expected": "Both items are still present in cart with quantities preserved.",
            },
            {
                "title": "Out-of-stock item shown in cart",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "Item in cart goes out of stock after it was added",
                "steps": [
                    "Open cart page",
                ],
                "expected": "Out-of-stock item shown with greyed-out state and 'Out of Stock' label; checkout button disabled for that seller group if only item.",
            },
            {
                "title": "Select-all and bulk delete",
                "category": "Happy Path",
                "priority": "P2",
                "preconditions": "Cart has 5+ items",
                "steps": [
                    "Tap 'Select All' checkbox",
                    "Tap 'Delete'",
                    "Confirm deletion",
                ],
                "expected": "All items removed; cart shows empty state; badge resets to 0.",
            },
        ],
    },

    # ── Promotion ─────────────────────────────────────────────────────────────
    {
        "name": "Promotion — Platform Voucher Redemption",
        "description": "Validation of Shopee SG platform-issued vouchers: free shipping, % discount, and fixed-amount vouchers.",
        "component": "Promotion",
        "source_type": "jira",
        "jira_key": "SPPT-2201",
        "agent": AGENTS["promotion"],
        "created_offset": 3,
        "cases": [
            {
                "title": "Apply valid platform % discount voucher at checkout",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "User holds a '15% off, min spend SGD 20, max cap SGD 8' platform voucher; cart total ≥ SGD 20",
                "steps": [
                    "Proceed to checkout",
                    "Tap 'Vouchers' → 'Add Voucher Code'",
                    "Enter voucher code and apply",
                ],
                "expected": "15% calculated on cart subtotal; discount capped at SGD 8; correct reduced total shown.",
            },
            {
                "title": "Voucher rejected when minimum spend not met",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "Cart total = SGD 15; voucher requires min spend SGD 20",
                "steps": [
                    "Enter voucher code on checkout",
                    "Tap 'Apply'",
                ],
                "expected": "Error message: 'Minimum spend of SGD 20 required'; voucher not applied; original total unchanged.",
            },
            {
                "title": "Expired voucher shows clear error",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "Voucher expiry date is yesterday",
                "steps": [
                    "Enter expired voucher code",
                    "Tap 'Apply'",
                ],
                "expected": "Error: 'Voucher has expired'; voucher not applied.",
            },
            {
                "title": "Voucher already claimed cannot be applied twice",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "User has already used this single-use voucher on a previous order",
                "steps": [
                    "Attempt to apply the same voucher code",
                ],
                "expected": "Error: 'Voucher already used'; voucher not applied.",
            },
            {
                "title": "Platform voucher and seller voucher stack correctly",
                "category": "Happy Path",
                "priority": "P1",
                "preconditions": "User holds both a platform free-shipping voucher and a seller 10% voucher",
                "steps": [
                    "Apply seller voucher (seller-level discount applied)",
                    "Apply platform free-shipping voucher (shipping waived)",
                    "Review order summary",
                ],
                "expected": "Seller discount and free shipping both reflected; discounts do not cancel each other out.",
            },
            {
                "title": "Voucher collected but not yet claimed appears in 'My Vouchers'",
                "category": "Regression",
                "priority": "P2",
                "preconditions": "User collected a voucher from the Voucher Centre",
                "steps": [
                    "Navigate to Me → My Vouchers",
                ],
                "expected": "Voucher listed under 'Available'; validity dates and discount details shown correctly.",
            },
        ],
    },
    {
        "name": "Promotion — Flash Sale",
        "description": "Test cases for Shopee SG Flash Sale participation: countdown timers, stock limits, per-user purchase caps.",
        "component": "Promotion",
        "source_type": "mr",
        "source_ref": "https://gitlab.shopee.io/promotion/flash-sale/-/merge_requests/418",
        "agent": AGENTS["promotion"],
        "created_offset": 1,
        "cases": [
            {
                "title": "Flash sale item purchasable at discounted price during active window",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "Flash sale is active; item has remaining stock; user has not hit per-user purchase cap",
                "steps": [
                    "Open Flash Sale page during active period",
                    "Tap on a flash sale item",
                    "Add to cart and proceed to checkout",
                    "Complete purchase",
                ],
                "expected": "Order placed at flash sale price, not original price; flash sale stock count decremented by 1.",
            },
            {
                "title": "Per-user limit enforced on flash sale item",
                "category": "Boundary",
                "priority": "P0",
                "preconditions": "Flash sale item has per-user limit = 1; user has already purchased 1 unit",
                "steps": [
                    "Attempt to add flash sale item to cart again",
                ],
                "expected": "'Limit reached' message shown; add-to-cart button disabled for that item.",
            },
            {
                "title": "Flash sale countdown timer accuracy",
                "category": "Regression",
                "priority": "P1",
                "preconditions": "Flash sale starts in < 5 minutes",
                "steps": [
                    "Open Flash Sale page with upcoming session",
                    "Observe countdown timer for 60 seconds",
                    "Compare timer value against device system clock",
                ],
                "expected": "Countdown decrements in real time, within ±1s of system clock; auto-refreshes when timer hits zero.",
            },
            {
                "title": "Flash sale item sold-out state displayed correctly",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "Flash sale item stock = 0 during active session",
                "steps": [
                    "View Flash Sale page",
                ],
                "expected": "Item shows 'Sold Out' badge; add-to-cart/buy-now disabled; item remains visible but not purchasable.",
            },
            {
                "title": "Flash sale price reverts after session ends",
                "category": "Regression",
                "priority": "P1",
                "preconditions": "Flash sale session ends while item is in cart",
                "steps": [
                    "Add flash sale item to cart during active session",
                    "Wait for flash sale session to expire",
                    "Return to cart",
                ],
                "expected": "Cart shows updated price at original (non-flash) price; user is notified of price change before checkout.",
            },
            {
                "title": "Cannot checkout flash sale item below minimum purchase",
                "category": "Boundary",
                "priority": "P2",
                "preconditions": "Flash sale item has minimum purchase quantity = 2",
                "steps": [
                    "Add only 1 unit of flash sale item to cart",
                    "Proceed to checkout",
                ],
                "expected": "System prompts user to meet minimum quantity; checkout blocked until quantity ≥ 2.",
            },
        ],
    },

    # ── Payment ───────────────────────────────────────────────────────────────
    {
        "name": "Payment — ShopeePay Wallet",
        "description": "Functional test cases for ShopeePay wallet operations: top-up via PayNow, balance checks, and payment authorisation.",
        "component": "Payment",
        "source_type": "jira",
        "jira_key": "SPPY-3105",
        "agent": AGENTS["payment"],
        "created_offset": 7,
        "cases": [
            {
                "title": "Top up ShopeePay via PayNow (NRIC-linked)",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "User has ShopeePay activated; Singapore bank account linked to PayNow via NRIC",
                "steps": [
                    "Navigate to ShopeePay → Top Up",
                    "Select PayNow as top-up method",
                    "Enter SGD 50 and confirm",
                    "Complete PayNow transfer from banking app",
                ],
                "expected": "ShopeePay balance increases by SGD 50 within 30 seconds; top-up transaction visible in transaction history.",
            },
            {
                "title": "ShopeePay payment requires PIN for orders ≥ SGD 100",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "User has ShopeePay PIN set; order total = SGD 120; sufficient ShopeePay balance",
                "steps": [
                    "Select ShopeePay at checkout",
                    "Tap 'Place Order'",
                    "Enter 6-digit PIN when prompted",
                ],
                "expected": "PIN dialog appears for orders ≥ SGD 100; payment proceeds only after correct PIN; wrong PIN shows error and increments fail count.",
            },
            {
                "title": "Insufficient ShopeePay balance shows clear error",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "ShopeePay balance = SGD 10; order total = SGD 50",
                "steps": [
                    "Select ShopeePay at checkout",
                    "Tap 'Place Order'",
                ],
                "expected": "'Insufficient balance' error shown; option to top up presented inline; order not placed.",
            },
            {
                "title": "ShopeePay account frozen after 5 wrong PIN attempts",
                "category": "Security",
                "priority": "P0",
                "preconditions": "User knows the correct PIN but will deliberately enter wrong PIN",
                "steps": [
                    "Attempt ShopeePay payment",
                    "Enter incorrect PIN 5 times consecutively",
                ],
                "expected": "After 5th failure, ShopeePay is temporarily frozen; user prompted to reset PIN via OTP; payment blocked.",
            },
            {
                "title": "Top-up limit: single top-up ≤ SGD 1000",
                "category": "Boundary",
                "priority": "P1",
                "preconditions": "User attempts to top up SGD 1001",
                "steps": [
                    "Navigate to Top Up",
                    "Enter SGD 1001",
                    "Tap Confirm",
                ],
                "expected": "Error: 'Top-up amount exceeds single transaction limit of SGD 1,000'; top-up blocked.",
            },
            {
                "title": "Transaction history displays correct debit/credit entries",
                "category": "Regression",
                "priority": "P2",
                "preconditions": "User has made at least 3 ShopeePay transactions",
                "steps": [
                    "Navigate to ShopeePay → Transaction History",
                ],
                "expected": "Transactions listed in descending date order; each entry shows correct amount (+ for top-ups, - for payments), merchant name, and timestamp.",
            },
        ],
    },
    {
        "name": "Payment — Credit Card & 3DS",
        "description": "Test cases for credit/debit card payment including Visa/Mastercard 3D Secure authentication on Shopee SG.",
        "component": "Payment",
        "source_type": "manual",
        "agent": AGENTS["payment"],
        "created_offset": 14,
        "cases": [
            {
                "title": "Add new Visa credit card and pay",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "User has no saved cards; valid Visa test card available",
                "steps": [
                    "At checkout, select 'Credit/Debit Card'",
                    "Tap 'Add New Card'",
                    "Enter card number, expiry, CVV, and cardholder name",
                    "Tap 'Save and Pay'",
                    "Complete 3DS OTP from issuing bank",
                ],
                "expected": "Payment processed; order placed; card optionally saved for future use if user consents.",
            },
            {
                "title": "3DS OTP timeout handled gracefully",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "User is on 3DS OTP page",
                "steps": [
                    "Do not enter OTP",
                    "Wait for OTP to expire (typically 5 minutes)",
                ],
                "expected": "Page shows 'Session expired'; user redirected to checkout to retry; order not placed; no double charge.",
            },
            {
                "title": "Declined card shows actionable error message",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "Card is set to decline (insufficient funds scenario)",
                "steps": [
                    "Select saved declined card at checkout",
                    "Tap 'Place Order'",
                    "Complete 3DS if required",
                ],
                "expected": "Error: 'Payment declined. Please check with your bank or use a different payment method.'; order remains in pending state or is cancelled.",
            },
            {
                "title": "Saved card can be removed from profile",
                "category": "Happy Path",
                "priority": "P2",
                "preconditions": "User has at least 1 saved card",
                "steps": [
                    "Navigate to Me → Payment → Saved Cards",
                    "Tap 'Remove' on a card",
                    "Confirm removal",
                ],
                "expected": "Card removed from list; no longer appears at checkout; confirmation toast shown.",
            },
        ],
    },

    # ── Logistics ─────────────────────────────────────────────────────────────
    {
        "name": "Logistics — Order Tracking & Delivery",
        "description": "Test cases for Shopee SG standard delivery tracking, delivery notification, and failed-delivery handling.",
        "component": "Logistics",
        "source_type": "jira",
        "jira_key": "SPLS-4033",
        "agent": FALLBACK_AGENT,
        "created_offset": 8,
        "cases": [
            {
                "title": "Order tracking page shows real-time shipment milestones",
                "category": "Happy Path",
                "priority": "P1",
                "preconditions": "Order status is 'Shipping'; tracking number assigned by seller",
                "steps": [
                    "Navigate to Me → My Purchases → 'Shipping' tab",
                    "Tap on order",
                    "Tap 'Track Shipment'",
                ],
                "expected": "Tracking page shows courier name, tracking ID, and at least 1 milestone (e.g., 'Parcel picked up'); milestones in chronological order.",
            },
            {
                "title": "Push notification sent when parcel out for delivery",
                "category": "Integration",
                "priority": "P1",
                "preconditions": "User has Shopee app notifications enabled; order enters 'Out for Delivery' status",
                "steps": [
                    "Background the app",
                    "Simulate courier system updating status to 'Out for Delivery'",
                ],
                "expected": "Push notification arrives within 2 minutes with message 'Your parcel is on its way!'; tapping opens order tracking page.",
            },
            {
                "title": "Failed delivery recorded and user notified",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "Courier marks delivery as 'Failed — recipient not available'",
                "steps": [
                    "Check order tracking after failed delivery event",
                ],
                "expected": "Tracking milestone shows 'Delivery attempted — not home'; user receives notification with re-delivery instructions or self-collection option.",
            },
            {
                "title": "Order auto-completes after 7 days of 'Delivered' status",
                "category": "Regression",
                "priority": "P2",
                "preconditions": "Order marked 'Delivered' 7+ days ago with no dispute raised",
                "steps": [
                    "Check order status",
                ],
                "expected": "Order status changes to 'Completed'; seller receives payment release; buyer can no longer open return request.",
            },
            {
                "title": "Estimated delivery date shown on order page",
                "category": "Happy Path",
                "priority": "P2",
                "preconditions": "Order placed with standard shipping; seller has not yet shipped",
                "steps": [
                    "View order details page",
                ],
                "expected": "Estimated delivery date range displayed (e.g., '10–14 May'); date range reflects courier SLA for Singapore addresses.",
            },
        ],
    },
    {
        "name": "Logistics — Return & Refund",
        "description": "Return merchandise authorisation (RMA) and refund flow for Shopee SG buyers.",
        "component": "Logistics",
        "source_type": "manual",
        "agent": FALLBACK_AGENT,
        "created_offset": 20,
        "cases": [
            {
                "title": "Buyer initiates return within return window",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "Order status is 'Completed'; return window (typically 7 days) has not expired",
                "steps": [
                    "Navigate to order details",
                    "Tap 'Return/Refund'",
                    "Select reason: 'Item not as described'",
                    "Upload 2 photos of the item",
                    "Submit return request",
                ],
                "expected": "Return request created; seller notified; order status changes to 'Return/Refund in Progress'; buyer can track request status.",
            },
            {
                "title": "Return request rejected after return window expires",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "Order completed more than 7 days ago",
                "steps": [
                    "Navigate to order details",
                    "Attempt to tap 'Return/Refund'",
                ],
                "expected": "'Return/Refund' option is hidden or disabled; tooltip shows return window has closed.",
            },
            {
                "title": "Refund credited to ShopeePay after return approved",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "Return request approved by seller or Shopee admin; original payment was via ShopeePay",
                "steps": [
                    "Return parcel using provided label",
                    "Courier confirms parcel received by seller",
                    "Return request closes as 'Approved'",
                ],
                "expected": "Refund amount credited to buyer's ShopeePay balance within 3–5 business days; refund transaction visible in transaction history.",
            },
            {
                "title": "Partial refund for damaged item — correct amount",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "Buyer and seller agree on 50% partial refund for a damaged item",
                "steps": [
                    "Seller/Shopee admin sets partial refund amount",
                    "Buyer confirms partial refund",
                ],
                "expected": "Only 50% of item price refunded; order closes; correct amounts shown in refund history.",
            },
            {
                "title": "Return shipping label generated correctly",
                "category": "Regression",
                "priority": "P2",
                "preconditions": "Return request approved; Shopee arranges return shipping",
                "steps": [
                    "Open approved return request",
                    "Tap 'Download Return Label'",
                ],
                "expected": "PDF label generated with correct sender (buyer), recipient (seller/warehouse), and barcode; printable at standard A4 size.",
            },
        ],
    },

    # ── User & Auth ───────────────────────────────────────────────────────────
    {
        "name": "User & Auth — Registration & Login",
        "description": "Sign-up, phone OTP verification, login flows, and account security for Shopee SG.",
        "component": "User & Auth",
        "source_type": "manual",
        "agent": FALLBACK_AGENT,
        "created_offset": 30,
        "cases": [
            {
                "title": "Register new account with SG mobile number",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "New Singapore +65 mobile number not yet registered",
                "steps": [
                    "Open Shopee app → Register",
                    "Enter +65 phone number",
                    "Request OTP",
                    "Enter OTP received via SMS",
                    "Set password (8+ chars, at least 1 letter + 1 number)",
                    "Complete profile setup (optional name/email)",
                ],
                "expected": "Account created; user logged in; welcome screen shown; account appears in Shopee system with 'SG' region.",
            },
            {
                "title": "OTP expires after 60 seconds",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "OTP requested but not entered",
                "steps": [
                    "Wait 61 seconds after OTP is sent",
                    "Enter the original OTP",
                ],
                "expected": "Error: 'OTP has expired. Please request a new one.'; registration not completed.",
            },
            {
                "title": "Duplicate mobile number registration blocked",
                "category": "Edge Case",
                "priority": "P1",
                "preconditions": "Mobile number already registered",
                "steps": [
                    "Attempt to register with an existing mobile number",
                ],
                "expected": "Error: 'This phone number is already registered. Please log in instead.'; registration not completed.",
            },
            {
                "title": "Login with correct credentials",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "Active account exists",
                "steps": [
                    "Enter registered email or phone number",
                    "Enter correct password",
                    "Tap 'Login'",
                ],
                "expected": "User logged in; redirected to home feed; session token set with 30-day expiry.",
            },
            {
                "title": "Account locked after 5 failed login attempts",
                "category": "Security",
                "priority": "P0",
                "preconditions": "Valid account with known password",
                "steps": [
                    "Enter correct username but wrong password 5 times",
                ],
                "expected": "Account temporarily locked for 30 minutes after 5th failure; message advises user to try later or reset password.",
            },
            {
                "title": "Password reset via SMS OTP",
                "category": "Happy Path",
                "priority": "P1",
                "preconditions": "User has forgotten password; registered phone accessible",
                "steps": [
                    "Tap 'Forgot Password' on login screen",
                    "Enter registered phone number",
                    "Enter OTP received via SMS",
                    "Set new password",
                ],
                "expected": "Password updated; user logged in automatically; old password no longer works.",
            },
        ],
    },

    # ── Product & Search ──────────────────────────────────────────────────────
    {
        "name": "Product & Search — Keyword Search & Filters",
        "description": "Search relevance, filter correctness, and sort order tests for Shopee SG product discovery.",
        "component": "Product & Search",
        "source_type": "jira",
        "jira_key": "SPSR-5210",
        "agent": AGENTS["promotion"],
        "created_offset": 4,
        "cases": [
            {
                "title": "Keyword search returns relevant results",
                "category": "Happy Path",
                "priority": "P0",
                "preconditions": "User is on home screen",
                "steps": [
                    "Tap search bar",
                    "Type 'wireless earbuds'",
                    "Press Search",
                ],
                "expected": "Results page shows products with 'wireless earbuds' in title or category; top 5 results are clearly relevant; sponsored items labelled 'Ad'.",
            },
            {
                "title": "Filter by price range narrows results correctly",
                "category": "Happy Path",
                "priority": "P1",
                "preconditions": "Search results page showing > 20 items",
                "steps": [
                    "Tap 'Filter' icon",
                    "Set price range SGD 10 – SGD 50",
                    "Tap 'Apply'",
                ],
                "expected": "All displayed products have price between SGD 10 and SGD 50 inclusive; result count updates.",
            },
            {
                "title": "Sort by 'Newest' shows most recently listed items first",
                "category": "Regression",
                "priority": "P2",
                "preconditions": "On search results page",
                "steps": [
                    "Tap 'Sort' → select 'Newest'",
                ],
                "expected": "Items sorted by listing date descending; first item's listing date ≥ all others on page.",
            },
            {
                "title": "Shopee Mall filter shows only mall sellers",
                "category": "Happy Path",
                "priority": "P1",
                "preconditions": "Search results include both mall and non-mall sellers",
                "steps": [
                    "Toggle 'Shopee Mall' filter",
                ],
                "expected": "Only items with Shopee Mall badge shown; non-mall sellers removed from results.",
            },
            {
                "title": "Search with typo returns corrected suggestions",
                "category": "Edge Case",
                "priority": "P2",
                "preconditions": "User types a common misspelling",
                "steps": [
                    "Search for 'wireles earbud'",
                ],
                "expected": "Results shown for 'wireless earbuds'; correction banner: 'Showing results for wireless earbuds'; option to search original typo available.",
            },
            {
                "title": "No-result state shows helpful suggestions",
                "category": "Edge Case",
                "priority": "P2",
                "preconditions": "Search term is highly obscure with zero results",
                "steps": [
                    "Search for a nonsense string, e.g., 'xqz99tplm'",
                ],
                "expected": "Empty state with message 'No results found'; suggested popular searches displayed below.",
            },
            {
                "title": "Recently viewed items appear in search history",
                "category": "Regression",
                "priority": "P3",
                "preconditions": "User has viewed at least 3 products",
                "steps": [
                    "Tap search bar without typing",
                ],
                "expected": "Recent search terms and recently viewed item thumbnails shown beneath search bar.",
            },
        ],
    },
]


def seed():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")

    # Check existing suite names to avoid duplicates
    existing = {row[0] for row in db.execute("SELECT name FROM test_suites").fetchall()}

    inserted_suites = 0
    inserted_cases = 0

    for suite_def in SUITES:
        name = suite_def["name"]
        if name in existing:
            print(f"  SKIP (exists): {name}")
            continue

        agent_id, agent_name = suite_def["agent"]
        suite_id = str(uuid.uuid4())
        created = ts(suite_def.get("created_offset", 0))

        db.execute(
            """INSERT INTO test_suites
               (id, agent_id, agent_name, name, description, component,
                source_type, source_ref, jira_key, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                suite_id,
                agent_id,
                agent_name,
                name,
                suite_def.get("description", ""),
                suite_def.get("component", ""),
                suite_def.get("source_type", "manual"),
                suite_def.get("source_ref", ""),
                suite_def.get("jira_key", ""),
                created,
                created,
            ),
        )
        inserted_suites += 1

        for i, tc in enumerate(suite_def["cases"]):
            case_id = str(uuid.uuid4())
            steps_json = json.dumps(tc.get("steps", []), ensure_ascii=False)
            db.execute(
                """INSERT INTO test_cases
                   (id, suite_id, title, category, preconditions, steps,
                    expected, priority, order_index, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    case_id,
                    suite_id,
                    tc["title"],
                    tc.get("category", ""),
                    tc.get("preconditions", ""),
                    steps_json,
                    tc.get("expected", ""),
                    tc.get("priority", "P1"),
                    i,
                    created,
                    created,
                ),
            )
            inserted_cases += 1

        print(f"  ✓ [{suite_def['component']}] {name}  ({len(suite_def['cases'])} cases)")

    db.commit()
    db.close()
    print(f"\nDone. Inserted {inserted_suites} suites, {inserted_cases} test cases.")


if __name__ == "__main__":
    seed()

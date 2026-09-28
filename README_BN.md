# SK BATTLE v4 — Coin Deposit Request

## নতুন ফিচার
- প্রত্যেক User-এর ইউনিক ID: SK000001 ধরনের।
- User Wallet থেকে টাকা পাঠানোর পর Add SK Coin Request পাঠাতে পারে (টাকার পরিমাণ, চাওয়া Coin, Transaction ID/UTR, ঐচ্ছিক নোট)।
- Admin Panel-এর Coin Deposit Requests অংশে User ID-সহ Request দেখা যায়।
- Admin ব্যাংকে টাকা এসেছে যাচাই করে অনুমোদিত Coin amount লিখে Approve করলে User Wallet-এ Coin যোগ হয় এবং Transaction History-তে রেকর্ড হয়।
- Request Reject করা যায়; একই Request দ্বিতীয়বার Approve করা যায় না।

## চালানো
```bash
pip install -r requirements.txt
python app.py
```
Browser: http://127.0.0.1:5000

## Admin Login
ডিফল্ট পাসওয়ার্ড `change-me-now` (শুধু লোকাল টেস্টের জন্য)। প্রকাশের আগে `ADMIN_PASSWORD` environment variable সেট করে শক্তিশালী পাসওয়ার্ড ব্যবহার করো। `SECRET_KEY`-ও পরিবর্তন করো।

## গুরুত্বপূর্ণ
এটি লোকাল ডেমো। কোনো Bank API বা Payment Gateway যুক্ত নেই। টাকা নিজে ব্যাংকে যাচাই করে তারপর Approve করবে। বাস্তব অনলাইন ব্যবহারের আগে HTTPS, CSRF protection, নিরাপদ Admin credentials, deployment এবং backup যোগ করতে হবে।

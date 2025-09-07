export default function Footer() {
  return (
    <footer className="footer">
      <div className="container footer__row">
        <div>© {new Date().getFullYear()} Algo Trade — כל הזכויות שמורות.</div>
        <div className="footer__links">
          <a href="/#features">תכונות</a>
          <a href="/#how">איך זה עובד</a>
          <a href="/#pricing">תמחור</a>
        </div>
      </div>
    </footer>
  )
}

import { Link } from 'react-router-dom'
import '../styles/home.css'
import logoUrl from '../assets/logo.svg'
import DashboardWidget from '../components/DashboardWidget.jsx'


export default function Home() {
  return (
    <div className="home">
      {/* HERO */}
      <section className="hero container">
        <div className="hero__content">
          <img src={logoUrl} alt="Algo Trade Logo" className="hero__logo" />
          <h1 className="hero__title">
            אלגו־טרייד חכם, <span className="grad">מבוסס AI</span>
          </h1>
          <p className="hero__subtitle">
            הפוך קישורי חדשות ודוחות PDF לתובנות מסחר מסודרות – כולל זיהוי חברה, סימבולים, וסנטימנט
            עם הסתברויות לעלייה/ירידה/יציבות.
          </p>

          <div className="hero__ctas">
            <Link to="/auth" className="btn btn--primary">כניסה / הרשמה</Link>
            <a href="#features" className="btn btn--ghost">תכונות</a>
          </div>

          <div className="hero__cards">
            <div className="card glass">
              <h3>ניתוח מסמכים חכם</h3>
              <p>קלט של קישורים (HTML/PDF) → פלט תמציתי של 6 שורות, בעברית מלאה ומדויקת.</p>
            </div>
            <div className="card glass">
              <h3>חיבור לטלגרם</h3>
              <p>לכפתורי עליה/ירידה יש התנהגות חכמה – שליחת נתוני חברה אוטומטית או ביטול ללא רעש.</p>
            </div>
            <div className="card glass">
              <h3>שמירת היסטוריה</h3>
              <p>לוגים נשמרים ב־DataLog נפרד מה־Users, עם סינכרון ל־Frontend ב־WebSocket.</p>
            </div>
          </div>
        </div>

        <div className="hero__visual">
          <div className="visual-frame">
            <div className="visual-sheen"></div>
            <div className="fake-chart">
              <div className="bar" style={{'--h':'68%'}}></div>
              <div className="bar" style={{'--h':'42%'}}></div>
              <div className="bar" style={{'--h':'85%'}}></div>
              <div className="bar" style={{'--h':'50%'}}></div>
              <div className="bar" style={{'--h':'73%'}}></div>
            </div>
            <p className="visual-caption">הדגמה ויזואלית — החלף ל־GIF/תמונה משלך</p>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section id="features" className="features container">
        <h2>למה לבחור ב־Algo Trade?</h2>
        <div className="features__grid">
          <Feature
            title="פלט אחיד ומסודר"
            text="תמיד 6 שורות: שם חברה, סימבול ת״א/ארה״ב, והסתברויות. אין טקסטים מיותרים."
          />
          <Feature
            title="מטריצה? בנפרד."
            text="מזהים מטריצה בסוף ההודעה, לא שולחים ל־GPT, אבל מציגים בטלגרם ולוגים."
          />
          <Feature
            title="ממשק רספונסיבי"
            text="עמוד נחיתה מוקפד, מותאם מובייל/דסקטופ, טעינה מהירה ועיצוב נקי."
          />
          <Feature
            title="ארכיטקטורה נקייה"
            text="הפרדת DB: Users ו־DataLog, זרימה בטוחה של מידע, ותיעוד ברור בקוד."
          />
        </div>
      </section>

      {/* DASHBOARD WIDGET – Tabs inside Home (no page navigation) */}
      <DashboardWidget defaultTab="positions" height={480} />

      {/* HOW IT WORKS */}
      <section id="how" className="how container">
        <h2>איך זה עובד?</h2>
        <ol className="how__steps">
          <li>
            <span className="step-badge">1</span>
            שולחים בטלגרם פוסט עם קישורים (HTML/PDF) ואופציונלית מטריצה בסוף.
          </li>
          <li>
            <span className="step-badge">2</span>
            השרת מנתח את התוכן ושולח תשובת GPT בפורמט קבוע לקבוצה.
          </li>
          <li>
            <span className="step-badge">3</span>
            לוחצים "עליה"/"ירידה" — המערכת סורקת את הטקסט ושולחת את פרטי החברה לערוץ היעד.
          </li>
        </ol>
        <div className="how__cta">
          <Link to="/auth" className="btn btn--primary">נתח עכשיו</Link>
        </div>
      </section>

      {/* PRICING */}
      <section id="pricing" className="pricing container">
        <h2>תמחור</h2>
        <div className="pricing__grid">
          <PriceCard plan="Basic" price="₪0" bullets={["גישה ל־Web", "דמו בלבד", "—"]} />
          <PriceCard plan="Pro" price="₪49" bullets={["גישה מלאה", "חיבור טלגרם", "לוגים עד 1000 רשומות"]} highlight />
          <PriceCard plan="Enterprise" price="בקרוב" bullets={["SLA", "תמיכה מורחבת", "התאמות"]} />
        </div>
      </section>

      {/* CTA */}
      <section className="cta container">
        <h3>מוכנים להתחיל?</h3>
        <p>צרו חשבון והתחילו להמיר קישורים לתובנות מסחר.</p>
        <Link to="/auth" className="btn btn--primary">להתחברות/הרשמה</Link>
      </section>
    </div>
  )
}

function Feature({ title, text }) {
  return (
    <div className="feature glass">
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  )
}

function PriceCard({ plan, price, bullets, highlight }) {
  return (
    <div className={`price glass ${highlight ? 'price--hl' : ''}`}>
      <div className="price__head">
        <h3>{plan}</h3>
        <div className="price__value">{price}</div>
      </div>
      <ul>
        {bullets.map((b, i) => <li key={i}>{b}</li>)}
      </ul>
      <Link to="/auth" className={`btn ${highlight ? 'btn--primary' : 'btn--ghost'}`}>להתחיל</Link>
    </div>
  )
}

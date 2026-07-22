"""Shared constants for public signup flows."""

COMPANY_SIZE_CHOICES = [
    ("1-5", "1–5"),
    ("6-10", "6–10"),
    ("11-25", "11–25"),
    ("26-50", "26–50"),
    ("51-100", "51–100"),
    ("101-250", "101–250"),
    ("250+", "250+"),
]

INDUSTRY_CHOICES = [
    ("metal", "Metal / Makine"),
    ("otomotiv", "Otomotiv"),
    ("elektronik", "Elektronik"),
    ("gida", "Gıda"),
    ("tekstil", "Tekstil"),
    ("kimya", "Kimya"),
    ("mobilya", "Mobilya"),
    ("plastik", "Plastik"),
    ("lojistik", "Lojistik"),
    ("yazilim", "Yazılım / Hizmet"),
    ("diger", "Diğer"),
]

EXPERIENCE_LEVEL_CHOICES = [
    ("student", "Öğrenci"),
    ("junior", "Junior"),
    ("mid", "Mid-Level"),
    ("senior", "Senior"),
    ("expert", "Uzman / Danışman"),
]

WORK_STYLE_CHOICES = [
    ("volunteer", "Gönüllü katkı"),
    ("freelance", "Freelance"),
    ("part_time", "Part-time"),
    ("full_time", "Full-time"),
    ("partnership", "İş ortaklığı"),
    ("integration", "Entegrasyon geliştiricisi"),
    ("unsure", "Henüz emin değilim"),
]

TECHNOLOGY_CHOICES = [
    ("python", "Python"),
    ("django", "Django"),
    ("postgresql", "PostgreSQL"),
    ("javascript", "JavaScript"),
    ("react", "React / Vue"),
    ("api", "REST API"),
    ("mobile", "Mobil uygulama"),
    ("ai", "AI / LLM"),
    ("devops", "DevOps"),
    ("other", "Diğer"),
]

TRIAL_MODULE_CHOICES = [
    ("stok", "Stok"),
    ("uretim", "Üretim"),
    ("satinalma", "Satınalma"),
    ("satis", "Satış"),
    ("kalite", "Kalite"),
    ("finans", "Finans"),
]

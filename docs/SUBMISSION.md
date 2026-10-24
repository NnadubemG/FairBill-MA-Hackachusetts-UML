# Submission text (copy into the form)

**Project:** FairBill MA
**Track:** Healthcare & Biotech
**Team:** Nnadubem Ganobi, Thomas Williamson, Erwin Coq, David Taveras
**Repo:** https://github.com/NnadubemG/FairBill-MA-Hackachusetts-UML
**Live site:** _[add public URL]_
**Video:** _[add YouTube/Vimeo link]_
**Kiro write-up:** `.kiro/KIRO_WRITEUP.md` in the repo

---

## Text description

**The problem.** Hospital bills are hard to read, and errors are common. Patients rarely know
whether a charge is normal. Since 2021, federal law has required every hospital to publish its
prices, but those files are huge machine-readable JSON and CSV dumps (25+ MB each) that no patient
can use.

**What FairBill MA does.** It turns those public files into a plain-language check of your own bill.

1. **Upload or enter your bill.** Upload a PDF or a phone photo, or type the lines in. An AI model
   reads the bill into line items.
2. **Confirm every line.** You see what was read, edit anything, and lines the model was unsure about
   are highlighted. Nothing is compared until you confirm.
3. **See what may be worth asking about.** Deterministic rules, not the AI, compare each line to real
   Massachusetts hospital prices. They point out charges outside the Massachusetts range, duplicate
   lines, unusual quantities, possible unbundling, and lines with no reference price. Every flag shows
   its reason and its data source and year.
4. **Get a letter.** Get an editable draft asking for an itemized bill, a coding review of the flagged
   lines, or financial assistance. It asks questions and never accuses. Copy, download, or print it.
5. **Compare hospitals.** For 19 common procedures (office and ER visits, labs, imaging, colonoscopy,
   MRI, CT), see each hospital's negotiated, cash, and gross prices side by side, with an accessible
   chart and a data table.

**What makes it trustworthy**
- **Numbers are never invented.** Every figure carries a `data_source` and `data_year`. If we don't
  have one, we show "—".
- **The AI never judges.** It only reads, rewrites in plain language, and drafts. Flags come from
  tested, deterministic code.
- **Careful language.** No accusatory words such as "overcharged" or "fraud". We say "may be worth
  asking about" and give the reason.
- **Private by design.** No login, nothing stored, nothing logged.

**Real data.** 122 price records parsed from the public price-transparency files of Lahey Hospital &
Medical Center and Beth Israel Deaconess Medical Center. A streaming parser handles the official CMS
file format.

**Built with:** Python 3.12, a vanilla-JavaScript web app (no build step), the Anthropic API, AWS
Lambda + CloudFront (SAM). 900+ automated tests, including Hypothesis property tests.

---

## Who benefits and how it scales

- **Who:** Massachusetts adults with a hospital bill they don't understand, especially uninsured,
  underinsured, and high-deductible patients, who pay closest to the listed price.
- **Accessibility:** no account, works on a phone, keyboard-operable with screen-reader labels and
  announcements, charts never rely on color alone (each has a data-table version), and plain-language
  text throughout. It also has a demo mode that works with no
  AI at all.
- **Equity:** the financial-assistance letter helps patients ask about charity care they may already
  qualify for.
- **Scale:** every US hospital publishes the same federally required file format. Adding a hospital
  means adding one line to a config file. Adding another state means adding that state's hospital
  files. Hosting is serverless and costs close to nothing when idle.

---

## Testing instructions for judges

**Online:** open the live site _[add URL]_. No login is needed.

**Locally (about 2 minutes):**
```bash
git clone https://github.com/NnadubemG/FairBill-MA-Hackachusetts-UML.git
cd FairBill-MA-Hackachusetts-UML
pip install -r requirements.txt
python -m app_server.server --port 8000
```
Then open http://127.0.0.1:8000/.

**Test path:**
1. Choose **"Test bill: ER visit priced against real MA data"**, then click **Use sample bill**.
2. Click **Check my bill**. Expect 5 flags: the ER visit and the CT scan above the Massachusetts
   range, a blood test listed twice, and a saline line with no reference price. The other lines show
   "Nothing stood out".
3. Click **Draft a letter**, then **Ask for a coding review**, then **Create my letter**.
4. Click **Compare prices** in the top menu and choose any procedure.

All bills in the repo are fictional. Uploading a PDF is read automatically only when an AI key is
configured. Otherwise, use the test bill or type the lines in.

# Excel Output Template

## File Naming
[UniversityName]-programmes.xlsx
Example: manchester-programmes.xlsx

---

## Column Structure

| Col | Header | Content |
|---|---|---|
| A | Course Name | Formatted degree name per naming rules |
| B | Degree Level | Bachelor / Associate / Diploma |
| C | Programme Page URL | =HYPERLINK() formula |
| D | Duration | e.g. 4 years / 24 months / 180 ECTS |
| E | Tuition Fee | Currency + period |
| F | Medium of Instruction | English / Korean / Japanese / etc. |
| G | Needs Manual Check | Yes / No |

## Country-Specific Extra Columns
- Australia: add CRICOS Code after column G
- Korea/Japan: add Teaching Track (English / Local medium)
- Indonesia: add Programme Code (S1 / D3 / D4)
- Australia/UK: add Intakes column

---

## Colour Logic

### Row Colour Decision Tree

```
Is it NMC: Yes?
    YES → Yellow (FFF2CC)
    NO  → Is it a Diploma or Associate?
              YES → Orange (FCE4D6)
              NO  → Is it English-medium at non-English university?
                        YES → Green alternating (E2EFDA / EBF5E1)
                        NO  → Blue alternating (D6E4F0 / FFFFFF)
```

### Colour Codes Summary

| Colour | Hex | Used For |
|---|---|---|
| Yellow | FFF2CC | NMC: Yes — any degree type |
| Orange | FCE4D6 | Diploma and Associate — NMC: No |
| Green light | E2EFDA | English-medium row 1 at non-English unis |
| Green lighter | EBF5E1 | English-medium row 2 alternating |
| Blue light | D6E4F0 | Standard Bachelor row 1 |
| White | FFFFFF | Standard Bachelor row 2 alternating |
| Dark navy | 1F3864 | Header row background |

---

## Font Colour Codes

| Font Colour | Hex | Used For |
|---|---|---|
| Black | 000000 | Standard text |
| Amber/Brown | 7F6000 | NMC: Yes text |
| Dark green | 375623 | English-medium at non-English university |
| Dark orange | 833C00 | Diploma and Associate degree rows |
| Blue underline | 0563C1 | URL column |
| White | FFFFFF | Header row text |

---

## Summary Block (paste at top of sheet or in a second tab)

| Field | Value |
|---|---|
| University | [Name] |
| Country | [Country] |
| Date Scraped | [Date] |
| Total Programmes | [Number] |
| Bachelor's | [Number] |
| Associate | [Number] |
| Diploma | [Number] |
| NMC: Yes | [Number] |
| NMC: No | [Number] |
| Scraping Method | [1-9] |
| Notes | [Any flags or issues] |

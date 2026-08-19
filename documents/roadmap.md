# Roadmap

Source of truth for what this project builds, in what order, and under which
constraints. Update it whenever scope changes, do not let it drift from
reality.

## Subject

Master's thesis, "Εξαγωγή Ευφυών Αναλύσεων από Δεδομένα Ηλεκτρονικού Εμπορίου"
(Extraction of Intelligent Analytics over Business Data).

Extract predictions and statistics that drive the marketing and sales decisions
of an e-commerce business, from its own transaction data, using data mining and
machine learning.

Submitted to the interdepartmental postgraduate programme «Διοίκηση και
Οικονομική των Τηλεπικοινωνιακών Δικτύων και Πληροφοριακών Συστημάτων»
(Management and Economics of Telecommunication Networks and Information
Systems), National and Kapodistrian University of Athens, run jointly by the
Department of Informatics and Telecommunications and the Department of
Economics.

The programme pairing is a scope constraint, not a formality. The work is read
by both sides, so a result that is technically sound but economically
uninterpretable, or an economic claim the data cannot support, both fail.

| Role | Person |
| --- | --- |
| Supervisor | Ευστάθιος Χατζηευθυμιάδης, Καθηγητής, ΕΚΠΑ |
| Examiner | Κωνσταντίνος Κολομβάτσος, Επίκουρος Καθηγητής, Πανεπιστήμιο Θεσσαλίας |
| Examiner | Μιλτιάδης Κυριακάκος, ΕΔΙΠ, ΕΚΠΑ |

## Questions the business asks

The analytical scope started from what real customers said they care about:

1. Products with the highest sales.
2. Customers with the most purchases.
3. Regions with the most sales.
4. Time periods when sales peak.
5. Products with the most refunds.
6. Sales per price range.
7. Sales per product characteristic.

Extended, on top of the original brief, with the economics that decide whether
any of the above is worth acting on: GMV, repeat customers, and profitability.

Extended again with growth accounting: the six-flow revenue decomposition and
concentration measures from the quantitative product-market-fit literature.
These are business-model agnostic, which is what lets the same system serve a
subscription store, a one-off gift retailer and a wholesaler without
recalibration.

## Academic direction

Set by the supervisor, these are requirements and not suggestions:

- **Frequent itemsets.** Mine the itemsets that reveal which products correlate
  in the available data.
- **Clustering, nested.** Cluster on parameters that matter, for example region
  and time, then cluster again *within* each cluster on additional parameters,
  forming a tree. Extract the insight from each cluster.
- **Prediction techniques** on top.
- **Reading**: Han, Kamber and Pei, *Data Mining: Concepts and Techniques*, 3rd
  edition, chapters 2, 3, 6 and 10, covering preprocessing, frequent itemsets
  and clustering.
- Algorithms are implemented by us with standard Python libraries (pandas,
  scikit-learn, mlxtend, statsmodels). No MindsDB in the graded core.

## Data

UCI **Online Retail II**. Public, citable, reproducible, and the dataset behind
Chen, Sain and Guo (2012), the RFM segmentation paper this work builds on. It
carries cancelled invoices, which is what makes the refunds question
answerable.

Its limits shape the design and must be stated in the manuscript:

- No cost of goods sold and no marketing spend.
- No structured product category, only a free-text description.
- Geography only at country granularity.

## Honesty rule for profitability

The dataset cannot answer "am I profitable" or "when will I be profitable" as a
measured fact, because it contains neither costs nor acquisition spend.

So the profitability module is a **scenario tool, never a claim**. It takes
explicit, configurable assumptions for gross margin and customer acquisition
cost, combines them with the forecast growth curve, and reports projected gross
profit, LTV:CAC, and payback period as a sensitivity analysis over those
inputs. Published benchmarks (LTV:CAC of 3:1, payback of 6 to 12 months, margin
bands by category) are cited as reference points, not as this business's
numbers.

This has to be stated plainly in the code docstrings, in the API responses, and
in the thesis discussion. Do not let a scenario output get presented as a
measurement anywhere.

## Presentation

- FastAPI JSON endpoints for every insight.
- Jupyter notebooks under `notebooks/` for the experiments and the figures the
  manuscript uses.
- Metabase for dashboards, reading the same result tables.
- No custom frontend.

## Genericity

Analytics never read a vendor-specific schema. Ingestion goes through a
`DataSourceAdapter` into a canonical model (`Customer`, `Product`, `Region`,
`Order`, `OrderItem`, `Return`), all tenant-scoped.

That canonical line is published as a data contract, documented in
[ingestion-contract.md](ingestion-contract.md), with three delivery routes:

| Route | Who moves the data | Needs code |
| --- | --- | --- |
| File export | The merchant exports, the system reads | Yes, one adapter per layout |
| `POST /api/v1/ingestion/transactions` | The merchant pushes | No |
| Read of the merchant's own database | The system pulls, given a query and a column mapping | No |

Validity rules live once, in `app/ingestion/normalisation.py`, so no route can
accept what another rejects.

## Delivery

Small PRs, each independently green. Sequence:

| # | Deliverable | Thesis chapter |
| --- | --- | --- |
| 1 | Bootstrap from the `yap` template | none |
| 2 | Thesis LaTeX skeleton, build tooling, CI | structure |
| 3 | Canonical domain models, migration, repositories | 3 |
| 4 | `DataSourceAdapter` + Online Retail II importer | 3 |
| 5 | Descriptive analytics for the seven questions | 4 |
| 6 | Business metrics: GMV, repeat rate, cohort retention, RFM | 7 |
| 7 | Frequent itemset mining, association rules | 5 |
| 8 | Nested clustering, region/time then RFM, evaluation | 6 |
| 9 | Sales forecasting, backtested | 7 |
| 10 | Profitability scenarios on the forecast | 7 |
| 11 | Growth accounting and PMF metrics | 7 |
| 12 | Metabase dashboards | none |
| 13 | Per-module methodology docs (`documents/methodology/`) | none |
| 14 | Thesis polish: abstracts, front matter, chapters 1/2/3/8 | all |

Chapters are drafted alongside the PR that produces their results, not batched
at the end.

The fourteen are delivered. Since then:

| Deliverable | Thesis chapter |
| --- | --- |
| Results written from the full dataset, every `TODO` removed | 3-7 |
| Posted-batch and database ingestion routes, shared validity rules | 3 |
| Appendices: code excerpts and the full sensitivity grid | Α, Β |
| All eighteen figures, generated from the imported dataset | 4-7 |

What remains needs the user, not code: `\thesismonth` in
`thesis/metadata.tex`, and confirmation of who signs as head of department.

## Rules

- **CI green before merge**, every PR, both the backend job and, when `thesis/`
  changes, the thesis job.
- **Tests accompany behaviour changes.** Coverage gate is 82%, do not merge
  through a regression in it.
- **Generic fixes go upstream.** If a problem belongs to any `yap`-based
  backend rather than to this thesis, fix it in `yap`, get it green there,
  merge, then pull it down with `./scripts/synchronize.sh`.
- **Statistical results are verified in a notebook**, printed or plotted,
  before the PR opens. "Tests pass" is not evidence that a model is correct.
- **Cite real sources.** Peer-reviewed work and books go in the bibliography.
  Vendor blog benchmarks, used only to justify assumed margins or CAC, are
  footnoted as industry estimates and kept out of it.

## Thesis manuscript

Greek, XeLaTeX with polyglossia, biber for the bibliography, in `thesis/`.

```bash
cd thesis && make                # local TeX Live
cd thesis && make ENGINE=docker  # no local TeX Live needed
```

Structure follows the department's template: cover, title page, English title
page, three-member committee page, copyright, plagiarism declaration,
acknowledgements, Greek abstract, English abstract, contents, list of tables,
list of figures, abbreviations, glossary, chapters, appendices lettered in
Greek, bibliography.

All names, ranks and dates live in `thesis/metadata.tex`. Edit that file, not
the front matter partials.

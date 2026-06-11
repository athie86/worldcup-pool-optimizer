import React from 'react';
import { InlineMath, BlockMath } from 'react-katex';

/**
 * Prediction model documentation.
 *
 * A formal explanation of the market-calibrated score model used by the
 * optimizer: bookmaker-implied probabilities, a Dixon-Coles prior,
 * entropy-regularized calibration, and expected pool payoff maximization.
 * All formulas are rendered with KaTeX (via react-katex).
 */

function SectionHeader({
  kicker,
  title,
  subtitle,
}: {
  kicker: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="mb-5">
      <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-slate-400 mb-1.5">
        {kicker}
      </div>
      <h3 className="text-lg font-bold text-slate-800 leading-snug">{title}</h3>
      {subtitle && <p className="text-sm text-slate-500 mt-1 max-w-3xl">{subtitle}</p>}
    </div>
  );
}

function Equation({ math, caption }: { math: string; caption?: string }) {
  return (
    <div className="my-5 rounded-xl border border-slate-200 bg-slate-50 px-5 py-4 overflow-x-auto">
      <BlockMath math={math} />
      {caption && (
        <div className="mt-3 font-mono text-[11px] uppercase tracking-[0.06em] text-slate-400">
          {caption}
        </div>
      )}
    </div>
  );
}

function Callout({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="my-6 rounded-xl border border-red-100 bg-red-50/60 px-5 py-4 max-w-3xl">
      <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-red-700 font-semibold mb-2">
        {label}
      </div>
      <p className="text-sm text-slate-700 m-0">{children}</p>
    </div>
  );
}

const PIPELINE = [
  { n: '01', title: 'Odds', body: 'Decimal prices are converted into margin-adjusted probabilities.' },
  { n: '02', title: 'Market targets', body: '1X2 and totals probabilities become calibration constraints.' },
  { n: '03', title: 'DC prior', body: 'A correlated low-score football prior is estimated.' },
  { n: '04', title: 'Entropy calibration', body: 'The prior is adjusted while preserving score structure.' },
  { n: '05', title: 'Optimizer', body: 'Scores are ranked by expected pool points.' },
];

const SCORING_RULES: [string, string][] = [
  ['Exact score', 'Highest rule value'],
  ['Correct winner and goal difference', 'Partial value'],
  ['Correct winner and team goals', 'Partial value'],
  ['Correct draw', 'Partial value'],
  ['Wrong result but one team goal correct', 'Low value'],
];

const FORMULA_INDEX = [
  {
    title: 'Forecast layer',
    body: 'Uses a Dixon-Coles prior to encode football score dependence and plausible low-score behavior.',
  },
  {
    title: 'Calibration layer',
    body: 'Uses KL regularization to preserve prior structure while matching market-implied probabilities.',
  },
  {
    title: 'Decision layer',
    body: 'Ranks all candidate scores by expected pool points rather than by raw score probability.',
  },
  {
    title: 'Risk diagnostics',
    body: 'Tracks variance, zero-point probability, score probability, calibration error, and tail mass.',
  },
];

export default function ModelDocsPage() {
  return (
    <div className="flex flex-col gap-5">
      {/* Page heading */}
      <div>
        <h2 className="text-xl font-bold text-slate-800">Prediction Model</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          How market prices become decision-grade score picks — a technical note
        </p>
      </div>

      {/* Hero / abstract */}
      <section className="card p-6 md:p-8">
        <SectionHeader kicker="01 / Abstract" title="From market prices to decision-grade score picks" />
        <p className="text-[15px] text-slate-600 leading-relaxed max-w-4xl">
          The World Cup Pool Optimizer implements a probabilistic score-prediction model designed to
          maximize expected points in a configurable football pool. The model converts bookmaker odds
          into normalized market-implied probabilities, fits a Dixon-Coles score distribution,
          calibrates that distribution to available totals markets through entropy-regularized
          optimization, and then ranks candidate score predictions by expected pool value. Unlike a
          model that merely selects the most likely score, this approach selects the prediction that
          maximizes expected scoring payoff under the pool&apos;s rules.
        </p>

        {/* Pipeline */}
        <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {PIPELINE.map((s) => (
            <div key={s.n} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="font-mono text-xs text-red-700 mb-3">{s.n}</div>
              <div className="text-sm font-semibold text-slate-800 mb-1">{s.title}</div>
              <p className="text-[13px] text-slate-500 m-0">{s.body}</p>
            </div>
          ))}
        </div>

        <Callout label="Core distinction">
          The recommended prediction is not necessarily the modal score. It is the score that maximizes
          expected payoff under the active pool scoring rules.
        </Callout>
      </section>

      {/* Market-implied probabilities */}
      <section className="card p-6 md:p-8">
        <SectionHeader
          kicker="02 / Market-Implied Probabilities"
          title="Bookmaker prices are transformed into normalized probability targets"
        />
        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          For each match, the model begins with decimal bookmaker odds for the three-way result market
          and, when available, over-under totals markets. Let the raw decimal odds for a market outcome{' '}
          <InlineMath math="k" /> be <InlineMath math="o_k" />. The model first converts odds into
          implied probabilities.
        </p>

        <Equation math={String.raw`q_k = \frac{1}{o_k}`} caption="Raw implied probability" />

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          Because bookmaker odds contain an overround, the raw implied probabilities generally do not
          sum to one. The application removes the margin proportionally:
        </p>

        <Equation
          math={String.raw`p_k = \frac{q_k}{\sum_{j \in \mathcal{M}} q_j}`}
          caption="Proportional margin removal"
        />

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          For a three-way result market, this produces normalized probabilities <InlineMath math="p_H" />
          , <InlineMath math="p_D" />, and <InlineMath math="p_A" />, corresponding to home win, draw,
          and away win. For totals markets, the same normalization is applied to the pair{' '}
          <InlineMath math={String.raw`\{\text{Over }x.5,\ \text{Under }x.5\}`} />, producing
          probabilities such as <InlineMath math="p_{O2.5}" /> and <InlineMath math="p_{U2.5}" />.
        </p>
      </section>

      {/* Dixon-Coles prior */}
      <section className="card p-6 md:p-8">
        <SectionHeader
          kicker="03 / Dixon-Coles Prior Score Distribution"
          title="A low-score correlation adjustment imposes football-score structure"
        />
        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          The model&apos;s first structural layer is a Dixon-Coles correlated score model. Let{' '}
          <InlineMath math="X" /> denote home goals and <InlineMath math="Y" /> denote away goals. A
          baseline independent Poisson model is specified as:
        </p>

        <Equation
          math={String.raw`\Pr(X=i,\,Y=j) = \frac{e^{-\lambda_H}\lambda_H^{\,i}}{i!}\,\frac{e^{-\lambda_A}\lambda_A^{\,j}}{j!}`}
          caption="Independent Poisson score model"
        />

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          The Dixon-Coles adjustment introduces a low-score dependence parameter <InlineMath math="\rho" />
          , modifying only the cells <InlineMath math="(0,0),(0,1),(1,0),(1,1)" />. The adjusted prior is:
        </p>

        <Equation
          math={String.raw`Q_{ij} = \frac{\tau(i,j;\lambda_H,\lambda_A,\rho)\,\operatorname{Pois}(i;\lambda_H)\,\operatorname{Pois}(j;\lambda_A)}{\displaystyle\sum_{u,v}\tau(u,v;\lambda_H,\lambda_A,\rho)\,\operatorname{Pois}(u;\lambda_H)\,\operatorname{Pois}(v;\lambda_A)}`}
          caption="Normalized Dixon-Coles prior"
        />

        <details className="my-6 rounded-xl border border-slate-200 bg-white max-w-3xl" open>
          <summary className="cursor-pointer px-4 py-3 font-mono text-xs uppercase tracking-[0.06em] text-slate-700 border-b border-slate-200">
            Dixon-Coles correction factor
          </summary>
          <div className="px-4 py-3">
            <Equation
              math={String.raw`\tau(i,j;\lambda_H,\lambda_A,\rho)=\begin{cases}1-\lambda_H\lambda_A\rho, & i=0,\ j=0,\\[2pt]1+\lambda_H\rho, & i=0,\ j=1,\\[2pt]1+\lambda_A\rho, & i=1,\ j=0,\\[2pt]1-\rho, & i=1,\ j=1,\\[2pt]1, & \text{otherwise.}\end{cases}`}
              caption="Low-score dependence adjustment"
            />
          </div>
        </details>

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          The parameters <InlineMath math="(\lambda_H,\lambda_A,\rho)" /> are fitted by minimizing
          weighted squared error between model-implied market probabilities and normalized bookmaker
          targets.
        </p>

        <Equation
          math={String.raw`\min_{\theta}\ \sum_{m \in \mathcal{T}} w_m\left[\pi_m\!\big(Q(\theta)\big)-p_m\right]^2`}
          caption="Weighted market fitting objective"
        />

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          For example, the model-implied three-way result probabilities are:
        </p>

        <Equation
          math={String.raw`\pi_H(Q)=\sum_{i>j}Q_{ij},\qquad \pi_D(Q)=\sum_{i=j}Q_{ij},\qquad \pi_A(Q)=\sum_{i<j}Q_{ij}`}
          caption="1X2 probabilities from the score matrix"
        />
      </section>

      {/* Entropy calibration */}
      <section className="card p-6 md:p-8">
        <SectionHeader
          kicker="04 / Entropy-Regularized Calibration"
          title="The final score matrix balances prior structure and market consistency"
        />
        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          After fitting the Dixon-Coles prior, the production model truncates the score space to a{' '}
          <InlineMath math="6 \times 6" /> grid covering scores from <InlineMath math="0" /> to{' '}
          <InlineMath math="5" /> goals for each team. The truncated matrix is renormalized, and
          probability mass outside the grid is recorded as tail mass.
        </p>

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          Let <InlineMath math="Q" /> be the normalized Dixon-Coles prior on the{' '}
          <InlineMath math="6 \times 6" /> grid. The calibrated matrix <InlineMath math="P" /> is
          obtained by solving:
        </p>

        <Equation
          math={String.raw`\min_{P}\ \operatorname{KL}(P\,\|\,Q) + \alpha \sum_{m \in \mathcal{T}} w_m\left[\pi_m(P)-p_m\right]^2`}
          caption="Entropy-regularized calibration problem"
        />

        <Equation
          math={String.raw`P_{ij} \ge 0,\qquad \sum_{i=0}^{5}\sum_{j=0}^{5}P_{ij}=1`}
          caption="Probability constraints"
        />

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          The Kullback-Leibler term is:
        </p>

        <Equation
          math={String.raw`\operatorname{KL}(P\,\|\,Q) = \sum_{i=0}^{5}\sum_{j=0}^{5} P_{ij}\log\!\left(\frac{P_{ij}}{Q_{ij}}\right)`}
          caption="Forward KL divergence from prior to calibrated matrix"
        />

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          The implementation parameterizes <InlineMath math="P" /> through a softmax over{' '}
          <InlineMath math="36" /> logits:
        </p>

        <Equation
          math={String.raw`P_{ij} = \frac{\exp(z_{ij})}{\displaystyle\sum_{u=0}^{5}\sum_{v=0}^{5}\exp(z_{uv})}`}
          caption="Softmax parameterization"
        />

        <Callout label="Calibration logic">
          The KL term keeps the final score distribution close to a plausible football prior. The
          market-error term forces consistency with the observed result and totals prices.
        </Callout>
      </section>

      {/* Expected points optimization */}
      <section className="card p-6 md:p-8">
        <SectionHeader
          kicker="05 / Expected Pool Points Optimization"
          title="The prediction is selected by payoff, not just probability"
        />
        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          Once the final score matrix <InlineMath math="P" /> is obtained, the application evaluates all
          candidate predictions:
        </p>

        <Equation
          math={String.raw`\mathcal{C}=\{(h,a):h,a \in \{0,1,2,3,4,5\}\}`}
          caption="Finite candidate score set"
        />

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          For a candidate prediction <InlineMath math="c=(h,a)" /> and an actual result{' '}
          <InlineMath math="s=(i,j)" />, the scoring system defines a payoff function{' '}
          <InlineMath math="R(c,s)" />. In standard mode, the payoff is the maximum point value among
          all enabled scoring rules that apply:
        </p>

        <Equation
          math={String.raw`R(c,s)=\max_{r \in \mathcal{R}}\left\{ v_r\,\mathbf{1}[\,r(c,s)=1\,]\right\}`}
          caption="Standard scoring payoff"
        />

        <div className="my-6 max-w-2xl overflow-hidden rounded-xl border border-slate-200 bg-white">
          {SCORING_RULES.map(([rule, value], idx) => (
            <div
              key={rule}
              className={`flex items-center justify-between gap-4 px-4 py-3 text-sm ${
                idx < SCORING_RULES.length - 1 ? 'border-b border-slate-100' : ''
              }`}
            >
              <span className="text-slate-700">{rule}</span>
              <span className="font-mono text-slate-500 text-right">{value}</span>
            </div>
          ))}
        </div>

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          In binary mode, the payoff is additive:
        </p>

        <Equation
          math={String.raw`R(c,s) = b_R\,\mathbf{1}[\operatorname{result}(c)=\operatorname{result}(s)] + b_T\,\mathbf{1}[h+a=i+j]`}
          caption="Binary scoring payoff"
        />

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          The expected value of a candidate is therefore:
        </p>

        <Equation
          math={String.raw`\operatorname{EP}(c) = \sum_{i=0}^{5}\sum_{j=0}^{5} P_{ij}\,R\big(c,(i,j)\big)`}
          caption="Expected pool points"
        />

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          The optimizer also computes variance and zero-point probability:
        </p>

        <Equation
          math={String.raw`\operatorname{Var}(c) = \operatorname{E}\!\big[R(c,S)^2\big] - \operatorname{EP}(c)^2`}
          caption="Candidate payoff variance"
        />

        <Equation
          math={String.raw`\Pr\!\big(R(c,S)=0\big) = \sum_{i=0}^{5}\sum_{j=0}^{5} P_{ij}\,\mathbf{1}[\,R(c,(i,j))=0\,]`}
          caption="Zero-point probability"
        />
      </section>

      {/* Interpretation */}
      <section className="card p-6 md:p-8">
        <SectionHeader
          kicker="06 / Interpretation"
          title="The application is a market-calibrated decision engine"
        />
        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          The model is best understood as a market-calibrated decision engine. The bookmaker markets
          provide externally disciplined probability targets. The Dixon-Coles layer imposes plausible
          football-score structure. The entropy calibration reconciles the score matrix with multiple
          market views without discarding the prior. The optimizer then converts the final predictive
          distribution into actionable pool picks.
        </p>

        <p className="text-[15px] text-slate-700 leading-relaxed max-w-4xl">
          The most important implication is that the recommended score is not necessarily the most
          probable score. A pool may award disproportionate value for exact scores, goal differences,
          correct draws, or partial matches. Therefore, the optimal prediction is the one with the
          highest expected pool payoff, not necessarily the modal outcome.
        </p>

        <div className="my-6 rounded-xl bg-red-700 px-6 py-5 text-white max-w-3xl">
          <p className="m-0 text-[15px] font-medium leading-relaxed">
            The model transforms score forecasting into a finite expected-points maximization problem
            under user-defined scoring rules.
          </p>
        </div>

        <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FORMULA_INDEX.map((card) => (
            <div key={card.title} className="rounded-xl border border-slate-200 bg-white p-5">
              <h4 className="text-sm font-semibold text-slate-800 mb-2">{card.title}</h4>
              <p className="text-[13px] text-slate-500 m-0">{card.body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

import Link from "next/link";

const Section = ({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) => (
  <section id={id} className="scroll-mt-6">
    <h2 className="mb-3 text-base font-semibold uppercase tracking-widest text-gray-500">
      {title}
    </h2>
    <div className="glass-card p-5 text-sm leading-relaxed text-gray-300">
      {children}
    </div>
  </section>
);

const Step = ({ n, children }: { n: number; children: React.ReactNode }) => (
  <div className="flex gap-3">
    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-bold text-white">
      {n}
    </span>
    <p>{children}</p>
  </div>
);

const Pill = ({ children }: { children: React.ReactNode }) => (
  <span className="inline-block rounded bg-white/10 px-2 py-0.5 font-mono text-xs text-gray-200">
    {children}
  </span>
);

const SourceBadge = ({ label }: { label: string }) => (
  <span className="inline-block rounded-full border border-white/15 px-2 py-0.5 text-xs font-medium text-gray-400">
    {label}
  </span>
);

export default function HelpPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Help</h1>
        <p className="mt-1 text-sm text-gray-400">
          A quick guide to getting the most out of Citey.
        </p>
      </div>

      {/* Jump links — row 1: 4 items, row 2: 3 items, both centered */}
      <nav className="mb-8 flex flex-col items-center gap-2">
        <div className="flex flex-wrap justify-center gap-2">
          {[
            ["what-is-citey", "What is Citey?"],
            ["getting-started", "Getting Started"],
            ["importing", "Importing Papers"],
            ["sources", "Data Sources"],
          ].map(([id, label]) => (
            <a
              key={id}
              href={`#${id}`}
              className="rounded-full border border-white/10 px-3 py-1 text-xs font-medium text-gray-400 transition-colors hover:border-white/30 hover:text-white"
            >
              {label}
            </a>
          ))}
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          {[
            ["notifications", "Notifications"],
            ["settings", "Settings"],
            ["faq-link", "FAQ"],
          ].map(([id, label]) => (
            <a
              key={id}
              href={`#${id}`}
              className="rounded-full border border-white/10 px-3 py-1 text-xs font-medium text-gray-400 transition-colors hover:border-white/30 hover:text-white"
            >
              {label}
            </a>
          ))}
        </div>
      </nav>

      <div className="flex flex-col gap-6">
        {/* What is Citey */}
        <Section id="what-is-citey" title="What is Citey?">
          <p>
            Citey monitors your research papers and emails you whenever a new
            paper cites one of them. It pulls data from multiple academic
            databases (see{" "}
            <a href="#sources" className="text-gray-300 underline hover:text-white">
              Data Sources
            </a>
            ) so you get broad coverage regardless of your field.
          </p>
        </Section>

        {/* Getting Started */}
        <Section id="getting-started" title="Getting Started">
          <div className="flex flex-col gap-3">
            <Step n={1}>
              <strong className="text-white">Create an account</strong>{" "}
              by signing up with your email on the{" "}
              <Link href="/signup" className="text-gray-300 underline hover:text-white">
                Sign In
              </Link>{" "}
              page.
            </Step>
            <Step n={2}>
              <strong className="text-white">Import your papers</strong>{" "}
              from the{" "}
              <Link href="/dashboard" className="text-gray-300 underline hover:text-white">
                Dashboard
              </Link>
              . Click <Pill>Add Papers</Pill> and paste a DOI, arXiv URL,
              author profile URL, or your name. Citey handles the rest.
            </Step>
            <Step n={3}>
              Citey will check for new citations automatically and email you
              when it finds any.
            </Step>
          </div>
        </Section>

        {/* Importing Papers */}
        <Section id="importing" title="Importing Papers">
          <div className="flex flex-col gap-4">
            <p>
              Click <Pill>Add Papers</Pill> on the Dashboard and paste anything
              into the single input field. Citey auto-detects what you pasted
              and handles the lookup.
            </p>

            <div className="flex flex-col gap-2.5">
              {/* arXiv */}
              <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
                <p className="mb-1 font-semibold text-white">arXiv URL or paper ID</p>
                <p className="text-xs text-gray-400">
                  Paste a full URL (e.g.{" "}
                  <Pill>https://arxiv.org/abs/2310.06825</Pill>) or a bare ID
                  like <Pill>2310.06825</Pill>. Citey looks up the paper on
                  Semantic Scholar and shows the author list so you can select
                  yourself and import all your papers.
                </p>
              </div>

              {/* DOI */}
              <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
                <p className="mb-1 font-semibold text-white">DOI or doi.org URL</p>
                <p className="text-xs text-gray-400">
                  Paste a bare DOI (e.g.{" "}
                  <Pill>10.48550/arXiv.2310.06825</Pill>) or a full{" "}
                  <Pill>https://doi.org/…</Pill> link. If your author profile is
                  already linked, the paper is added immediately. Otherwise Citey
                  shows the author list so you can link your profile first.
                </p>
              </div>

              {/* Author name */}
              <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
                <p className="mb-1 font-semibold text-white">
                  Author name{" "}
                </p>
                <p className="text-xs text-gray-400">
                  Type your name and Citey searches{" "}
                  <strong className="text-gray-300">OpenAlex</strong> and{" "}
                  <strong className="text-gray-300">Semantic Scholar</strong> in
                  parallel, showing matching profiles with affiliation and h-index.
                  Select yours to import all your papers in one step.
                </p>
                <p className="mt-1.5 text-xs text-gray-500">
                  After import, Citey automatically cross-checks{" "}
                  <strong className="text-gray-400">PubMed</strong>,{" "}
                  <strong className="text-gray-400">NASA ADS</strong>,{" "}
                  <strong className="text-gray-400">INSPIRE-HEP</strong>, and{" "}
                  <strong className="text-gray-400">DBLP</strong> for any
                  additional papers the primary source may have missed.
                </p>
              </div>

              {/* INSPIRE */}
              <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
                <p className="mb-1 font-semibold text-white">INSPIRE-HEP author profile URL</p>
                <p className="text-xs text-gray-400">
                  Paste your profile URL (e.g.{" "}
                  <Pill>https://inspirehep.net/authors/1234567</Pill>). Citey
                  imports all papers from that INSPIRE profile directly, including
                  JACoW conference proceedings that other databases miss.
                </p>
              </div>

              {/* DBLP */}
              <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
                <p className="mb-1 font-semibold text-white">DBLP author profile URL</p>
                <p className="text-xs text-gray-400">
                  Paste your DBLP profile URL (e.g.{" "}
                  <Pill>https://dblp.org/pid/12/3456</Pill>). Citey imports all
                  papers associated with that DBLP author entry, which has
                  near-complete ACM and IEEE conference coverage.
                </p>
              </div>
            </div>
          </div>
        </Section>

        {/* Data Sources */}
        <Section id="sources" title="Data Sources">
          <p className="mb-4">
            Citey uses the following databases when importing and checking for
            new citations. Each source is queried automatically; you do not
            need to choose.
          </p>
          <div className="flex flex-col gap-3">
            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-semibold text-white">OpenAlex</span>
                <SourceBadge label="Primary" />
                <SourceBadge label="All Fields" />
              </div>
              <p className="text-xs text-gray-400">
                ~250 million works. The primary source for author profiles and
                citation tracking across all disciplines.
              </p>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-semibold text-white">Semantic Scholar</span>
                <SourceBadge label="Primary" />
                <SourceBadge label="CS · AI · Bio" />
              </div>
              <p className="text-xs text-gray-400">
                ~200 million works. Strong on CS, AI/ML, and biomedical
                literature. Also used to look up paper authors by arXiv URL.
              </p>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-semibold text-white">PubMed</span>
                <SourceBadge label="Cross-Source Boost" />
                <SourceBadge label="Biomedical" />
              </div>
              <p className="text-xs text-gray-400">
                35 million records from NCBI. Fills in clinical and life-science
                papers that OpenAlex and S2 may miss. Applied automatically
                after every import.
              </p>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-semibold text-white">NASA ADS</span>
                <SourceBadge label="Cross-Source Boost" />
                <SourceBadge label="Astrophysics · Space" />
              </div>
              <p className="text-xs text-gray-400">
                Astrophysics Data System. Covers astronomy, astrophysics, and
                space-science literature. Requires an ADS API key configured on
                the server.
              </p>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-semibold text-white">INSPIRE-HEP</span>
                <SourceBadge label="Cross-Source Boost" />
                <SourceBadge label="HEP · Accelerator · Nuclear" />
              </div>
              <p className="text-xs text-gray-400">
                The canonical database for high-energy physics, accelerator
                physics, and nuclear physics. The only automated source for
                JACoW conference proceedings (NAPAC, IPAC, FEL, etc.) and
                CERN/SLAC/Fermilab preprints. No API key required.
              </p>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-semibold text-white">DBLP</span>
                <SourceBadge label="Cross-Source Boost" />
                <SourceBadge label="CS · ACM · IEEE" />
              </div>
              <p className="text-xs text-gray-400">
                Computer Science Bibliography. Near-complete coverage of ACM
                and IEEE conference and journal papers. Especially useful for
                older CS papers and proceedings that OpenAlex or S2 index
                without DOIs. No API key required.
              </p>
            </div>
          </div>

          <p className="mt-4 text-xs text-gray-500">
            <strong className="text-gray-400">Coverage note:</strong>{" "}
            all cross-source boosts apply automatically on every import. More
            sources are planned.
          </p>
        </Section>

        {/* Notifications */}
        <Section id="notifications" title="Notifications">
          <div className="flex flex-col gap-3">
            <p>
              When a new citation is detected, Citey creates a notification on
              your Dashboard and (if enabled) sends you an email digest.
            </p>
            <ul className="list-disc space-y-1.5 pl-5 text-gray-400">
              <li>
                <span className="text-gray-300">New citation emails</span>{" "}
                can be toggled in{" "}
                <Link href="/settings" className="text-gray-300 underline hover:text-white">
                  Settings
                </Link>{" "}
                under Notification Preferences.
              </li>
              <li>
                <span className="text-gray-300">New publication alerts</span>{" "}
                notify you when a new paper from your author profile is
                auto-added to your tracked list.
              </li>
              <li>
                <span className="text-gray-300">Notification email</span>{" "}
                defaults to your account email. You can set a different address
                in Settings.
              </li>
            </ul>
          </div>
        </Section>

        {/* Settings */}
        <Section id="settings" title="Settings">
          <div className="flex flex-col gap-2">
            <p className="mb-1">
              Accessible from the nav bar. Key options:
            </p>
            <ul className="list-disc space-y-1.5 pl-5 text-gray-400">
              <li>
                <span className="text-gray-300">Notification email</span>{" "}
                overrides the address that receives alerts.
              </li>
              <li>
                <span className="text-gray-300">Google Scholar URL</span>{" "}
                stores a link to your Scholar profile (display only, never
                scraped).
              </li>
              <li>
                <span className="text-gray-300">Tracked Works</span>{" "}
                lets you review and remove individual papers from your list.
              </li>
              <li>
                <span className="text-gray-300">Change linked author</span>{" "}
                resets your entire library and lets you re-link a different
                author profile.
              </li>
            </ul>
          </div>
        </Section>

        {/* FAQ link */}
        <Section id="faq-link" title="FAQ">
          <p>
            Have a specific question? Check the{" "}
            <Link href="/faq" className="text-gray-300 underline hover:text-white">
              FAQ page
            </Link>{" "}
            for common questions about how Citey works, data accuracy, and
            privacy.
          </p>
        </Section>
      </div>
    </div>
  );
}

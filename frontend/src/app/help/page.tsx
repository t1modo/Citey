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

      {/* Jump links */}
      <nav className="mb-8 flex flex-wrap gap-2">
        {[
          ["what-is-citey", "What is Citey?"],
          ["getting-started", "Getting Started"],
          ["importing", "Importing Papers"],
          ["sources", "Data Sources"],
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
              <strong className="text-white">Create an account</strong> — sign
              up with your email on the{" "}
              <Link href="/signup" className="text-gray-300 underline hover:text-white">
                Sign In
              </Link>{" "}
              page.
            </Step>
            <Step n={2}>
              <strong className="text-white">Link your author profile</strong>{" "}
              — from the{" "}
              <Link href="/dashboard" className="text-gray-300 underline hover:text-white">
                Dashboard
              </Link>
              , click <Pill>Add Papers</Pill> then use the{" "}
              <Pill>By Author</Pill> or <Pill>arXiv Link</Pill> tab to find and
              import all your papers at once.
            </Step>
            <Step n={3}>
              Citey will check for new citations automatically and email you
              when it finds any.
            </Step>
          </div>
        </Section>

        {/* Importing Papers */}
        <Section id="importing" title="Importing Papers">
          <div className="flex flex-col gap-5">
            {/* By Author */}
            <div>
              <p className="mb-1.5 font-semibold text-white">
                By Author name{" "}
                <span className="ml-1 font-normal text-gray-500">— recommended</span>
              </p>
              <p className="mb-2">
                Search your name in the <Pill>By Author</Pill> tab. Citey
                searches <strong className="text-white">OpenAlex</strong> and{" "}
                <strong className="text-white">Semantic Scholar</strong> in
                parallel and shows matching author profiles with affiliation and
                h-index to help you identify the right one. Select yours — all
                your papers are imported in one step.
              </p>
              <p className="text-xs text-gray-500">
                After import, Citey automatically cross-checks{" "}
                <strong className="text-gray-400">PubMed</strong>,{" "}
                <strong className="text-gray-400">NASA ADS</strong>,{" "}
                <strong className="text-gray-400">INSPIRE-HEP</strong>, and{" "}
                <strong className="text-gray-400">DBLP</strong> for any
                additional papers the primary source may have missed.
              </p>
            </div>

            <div className="border-t border-white/10" />

            {/* By arXiv */}
            <div>
              <p className="mb-1.5 font-semibold text-white">By arXiv link</p>
              <p>
                Paste an arXiv URL (e.g.{" "}
                <Pill>https://arxiv.org/abs/2310.06825</Pill>) into the{" "}
                <Pill>arXiv Link</Pill> tab. Citey looks up the paper on
                Semantic Scholar and shows you the author list — select
                yourself to import all papers by that author profile.
              </p>
            </div>

            <div className="border-t border-white/10" />

            {/* By DOI */}
            <div>
              <p className="mb-1.5 font-semibold text-white">By DOI</p>
              <p className="mb-2">
                Paste any DOI (e.g.{" "}
                <Pill>10.48550/arXiv.2310.06825</Pill>) into the{" "}
                <Pill>DOI</Pill> tab to add a single paper directly.
              </p>
              <ul className="list-disc space-y-1 pl-4 text-xs text-gray-500">
                <li>
                  If your author profile is already linked, Citey verifies you
                  are listed as an author before adding the paper.
                </li>
                <li>
                  If no profile is linked yet, Citey looks up the paper&apos;s
                  authors on Semantic Scholar and lets you pick yours — then
                  imports all papers by that author.
                </li>
              </ul>
            </div>
          </div>
        </Section>

        {/* Data Sources */}
        <Section id="sources" title="Data Sources">
          <p className="mb-4">
            Citey uses the following databases when importing and checking for
            new citations. Each source is queried automatically — you don&apos;t
            need to choose.
          </p>
          <div className="flex flex-col gap-3">
            {/* Row */}
            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-semibold text-white">OpenAlex</span>
                <SourceBadge label="primary" />
                <SourceBadge label="all fields" />
              </div>
              <p className="text-xs text-gray-400">
                ~250 million works. The primary source for author profiles and
                citation tracking across all disciplines.
              </p>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-semibold text-white">Semantic Scholar</span>
                <SourceBadge label="primary" />
                <SourceBadge label="CS · AI · bio" />
              </div>
              <p className="text-xs text-gray-400">
                ~200 million works. Strong on CS, AI/ML, and biomedical
                literature. Also used to look up paper authors by arXiv URL.
              </p>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-semibold text-white">PubMed</span>
                <SourceBadge label="cross-source boost" />
                <SourceBadge label="biomedical" />
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
                <SourceBadge label="cross-source boost" />
                <SourceBadge label="astrophysics · space" />
              </div>
              <p className="text-xs text-gray-400">
                Astrophysics Data System. Covers astronomy, astrophysics, and
                space-science literature — a major gap in OpenAlex and S2.
                Requires an ADS API key configured on the server.
              </p>
            </div>

            <div className="rounded-lg border border-white/10 bg-white/5 px-4 py-3">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-semibold text-white">INSPIRE-HEP</span>
                <SourceBadge label="cross-source boost" />
                <SourceBadge label="HEP · accelerator · nuclear" />
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
                <SourceBadge label="cross-source boost" />
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
            <strong className="text-gray-400">Coverage note —</strong> all
            cross-source boosts apply automatically on every import. More
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
                <span className="text-gray-300">New citation emails</span> —
                toggle in{" "}
                <Link href="/settings" className="text-gray-300 underline hover:text-white">
                  Settings
                </Link>{" "}
                → Notification Preferences.
              </li>
              <li>
                <span className="text-gray-300">New publication alerts</span>{" "}
                — get notified when a new paper from your author profile is
                auto-added to your tracked list.
              </li>
              <li>
                <span className="text-gray-300">Notification email</span> — by
                default, alerts go to your account email. You can set a
                different address in Settings.
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
                <span className="text-gray-300">Notification email</span> —
                override the address that receives alerts.
              </li>
              <li>
                <span className="text-gray-300">Google Scholar URL</span> —
                store a link to your Scholar profile (display only, never
                scraped).
              </li>
              <li>
                <span className="text-gray-300">Tracked Works</span> — review
                and remove individual papers from your list.
              </li>
              <li>
                <span className="text-gray-300">Change linked author</span> —
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

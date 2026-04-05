export default function Home() {
  return (
    <main className="min-h-screen">
      {/* ── Hero ── */}
      <section className="bg-gradient-to-br from-brand-50 to-white py-24 px-6 text-center">
        <div className="mx-auto max-w-3xl">
          <h1 className="text-5xl font-extrabold text-gray-900 leading-tight mb-6">
            {{HEADLINE}}
          </h1>
          <p className="text-xl text-gray-600 mb-10">{{SUBHEADLINE}}</p>
          <a
            href="{{CTA_URL}}"
            className="inline-block bg-brand-600 hover:bg-brand-700 text-white font-semibold text-lg px-8 py-4 rounded-xl shadow-lg transition-colors duration-200"
          >
            {{CTA_TEXT}}
          </a>
        </div>
      </section>

      {/* ── Features ── */}
      <section className="py-20 px-6 bg-white">
        <div className="mx-auto max-w-5xl">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-14">
            Everything you need
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
            {[
              {
                icon: "⚡",
                title: "{{FEATURE_1_TITLE}}",
                body: "{{FEATURE_1_BODY}}",
              },
              {
                icon: "🔒",
                title: "{{FEATURE_2_TITLE}}",
                body: "{{FEATURE_2_BODY}}",
              },
              {
                icon: "📈",
                title: "{{FEATURE_3_TITLE}}",
                body: "{{FEATURE_3_BODY}}",
              },
            ].map((f) => (
              <div
                key={f.title}
                className="bg-brand-50 rounded-2xl p-8 text-center shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="text-4xl mb-4">{f.icon}</div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                  {f.title}
                </h3>
                <p className="text-gray-600 text-sm leading-relaxed">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pricing ── */}
      <section className="py-20 px-6 bg-gray-50">
        <div className="mx-auto max-w-lg text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">
            Simple, transparent pricing
          </h2>
          <p className="text-gray-500 mb-10">{{PRICING_MODEL}}</p>
          <div className="bg-white rounded-2xl shadow-lg p-10 border border-gray-100">
            <div className="text-5xl font-extrabold text-brand-600 mb-2">
              {{PRICE}}
            </div>
            <p className="text-gray-500 mb-8">{{PRICING_MODEL}}</p>
            <a
              href="{{CTA_URL}}"
              className="block w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold text-lg py-4 rounded-xl shadow transition-colors duration-200"
            >
              {{CTA_TEXT}}
            </a>
          </div>
        </div>
      </section>

      {/* ── Testimonials ── */}
      <section className="py-20 px-6 bg-white">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-14">
            What our customers say
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {[
              {
                quote: "{{TESTIMONIAL_1_QUOTE}}",
                author: "{{TESTIMONIAL_1_AUTHOR}}",
                role: "{{TESTIMONIAL_1_ROLE}}",
              },
              {
                quote: "{{TESTIMONIAL_2_QUOTE}}",
                author: "{{TESTIMONIAL_2_AUTHOR}}",
                role: "{{TESTIMONIAL_2_ROLE}}",
              },
            ].map((t) => (
              <blockquote
                key={t.author}
                className="bg-brand-50 rounded-2xl p-8 shadow-sm"
              >
                <p className="text-gray-700 italic mb-6">&ldquo;{t.quote}&rdquo;</p>
                <footer>
                  <p className="font-semibold text-gray-900">{t.author}</p>
                  <p className="text-sm text-gray-500">{t.role}</p>
                </footer>
              </blockquote>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer CTA ── */}
      <section className="py-20 px-6 bg-brand-600 text-center">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-3xl font-bold text-white mb-6">
            Ready to get started?
          </h2>
          <a
            href="{{CTA_URL}}"
            className="inline-block bg-white text-brand-600 font-semibold text-lg px-8 py-4 rounded-xl shadow-lg hover:bg-brand-50 transition-colors duration-200"
          >
            {{CTA_TEXT}}
          </a>
        </div>
      </section>
    </main>
  );
}

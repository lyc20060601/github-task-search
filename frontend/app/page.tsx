"use client";

import { useState } from "react";

type SearchMode = "direct" | "smart" | "recommend";

type Project = {
  name: string;
  full_name: string;
  description: string | null;
  html_url: string;
  stars: number;
  language: string | null;
  updated_at: string;
  preliminary_score?: number;
};

type TaskSpec = {
  task: string | null;
  domain: string[];
  framework: string[];
  hardware: string[];
  must_have: string[];
  preferences: string[];
};

type SmartSearchResponse = {
  task_spec: TaskSpec;
  generated_queries: string[];
  repositories: Project[];
};

type Evidence = {
  source: string;
  reason: string;
};

type ScoreBreakdown = {
  task_match: number;
  completeness: number;
  must_have: number;
  maintenance: number;
  documentation: number;
  community: number;
  environment: number;
};

type Recommendation = {
  rank: number;
  full_name: string;
  html_url: string;
  description: string | null;
  stars: number;
  language: string | null;
  final_score: number;
  score_breakdown: ScoreBreakdown;
  repo_profile: RepoProfile | null;
  strengths: string[];
  weaknesses: string[];
  evidence: Record<string, Evidence>;
};

type RepoProfile = {
  framework?: string | null;
  tasks?: string[];
  domains?: string[];
  has_training_code?: boolean | null;
  training_entry?: string | null;
  has_custom_dataset_support?: boolean | null;
  has_pretrained_weights?: boolean | null;
  documentation_quality?: string | null;
  hardware_notes?: string | null;
  maintenance_notes?: string | null;
};

type RecommendSearchResponse = {
  task_spec: TaskSpec;
  generated_queries: string[];
  candidate_count: number;
  analyzed_count: number;
  recommendations: Recommendation[];
};

type RuntimeStatus = "success" | "failed" | "unknown" | "skipped";

type RuntimeReport = {
  full_name: string;
  clone_status: RuntimeStatus;
  environment_detected: RuntimeStatus;
  dependency_install_status: RuntimeStatus;
  entrypoint_detected: RuntimeStatus;
  smoke_test_status: RuntimeStatus;
  runtime_score: number | null;
  runtime_breakdown: Record<string, number>;
  runtime_status: RuntimeStatus;
  errors: string[];
  warnings: string[];
};

type ValidationState =
  | { status: "loading" }
  | { status: "complete"; report: RuntimeReport }
  | { status: "error"; message: string };

const placeholder = "描述你想寻找的 GitHub 项目，例如：找一个适合无人机语义分割的项目";
const apiBaseUrl = (
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  (process.env.VERCEL ? "/api/backend" : "http://127.0.0.1:8000")
).replace(/\/+$/, "");
const MAX_VISIBLE_ERRORS = 3;
const MAX_ERROR_LENGTH = 240;

const evidenceLabels: Record<string, string> = {
  has_training_code: "训练代码",
  has_custom_dataset_support: "自定义数据集",
  has_pretrained_weights: "预训练权重",
  framework: "技术框架",
  hardware_notes: "硬件要求",
};

function formatValues(values: string[]) {
  return values.length > 0 ? values.join("、") : "未指定";
}

function formatProfileValue(value: string | null | undefined) {
  return value?.trim() || "未知";
}

function formatProfileBoolean(value: boolean | null | undefined) {
  if (typeof value !== "boolean") return "未知";
  return value ? "是" : "否";
}

function ScoreItem({
  label,
  value,
  max,
}: {
  label: string;
  value: number;
  max: number;
}) {
  return (
    <div className="score-item">
      <div className="score-label">
        <span>{label}</span>
        <strong>{value}/{max}</strong>
      </div>
      <progress max={max} value={value} aria-label={`${label} ${value}/${max}`} />
    </div>
  );
}

const runtimeStages: Array<{
  key: keyof Pick<
    RuntimeReport,
    | "clone_status"
    | "environment_detected"
    | "entrypoint_detected"
    | "dependency_install_status"
    | "smoke_test_status"
  >;
  label: string;
}> = [
  { key: "clone_status", label: "Clone" },
  { key: "environment_detected", label: "环境识别" },
  { key: "entrypoint_detected", label: "运行入口" },
  { key: "dependency_install_status", label: "依赖安装" },
  { key: "smoke_test_status", label: "Smoke Test" },
];

const runtimeStatusDisplay: Record<RuntimeStatus, { symbol: string; label: string }> = {
  success: { symbol: "✅", label: "成功" },
  failed: { symbol: "❌", label: "失败" },
  unknown: { symbol: "?", label: "未知" },
  skipped: { symbol: "−", label: "已跳过" },
};

function truncateError(message: string) {
  const normalized = message.trim();
  return normalized.length > MAX_ERROR_LENGTH
    ? `${normalized.slice(0, MAX_ERROR_LENGTH)}…`
    : normalized;
}

function RuntimeValidationPanel({ state }: { state: ValidationState }) {
  if (state.status === "loading") {
    return (
      <section className="runtime-validation loading" role="status" aria-live="polite">
        <strong>正在创建隔离环境并验证项目，</strong>
        <span>这个过程可能需要几分钟……</span>
      </section>
    );
  }

  if (state.status === "error") {
    return (
      <section className="runtime-validation failed" role="alert">
        <strong>可运行性验证失败</strong>
        <p>{state.message}</p>
      </section>
    );
  }

  const { report } = state;
  const visibleErrors = report.errors
    .filter(Boolean)
    .slice(0, MAX_VISIBLE_ERRORS)
    .map(truncateError);

  return (
    <section className="runtime-validation complete" aria-label="可运行性验证结果">
      <div className="runtime-validation-heading">
        <h4>可运行性验证</h4>
        <strong className="runtime-score">
          Runtime Score：{Math.round(report.runtime_score ?? 0)}/100
        </strong>
      </div>
      <dl className="runtime-stage-list">
        {runtimeStages.map((stage) => {
          const status = report[stage.key];
          const display = runtimeStatusDisplay[status];
          return (
            <div key={stage.key}>
              <dt>{stage.label}</dt>
              <dd className={`runtime-stage ${status}`}>
                <span aria-hidden="true">{display.symbol}</span>
                <span>{display.label}</span>
              </dd>
            </div>
          );
        })}
      </dl>
      {visibleErrors.length > 0 && (
        <div className="runtime-errors" role="alert">
          <strong>主要失败原因</strong>
          <ul>
            {visibleErrors.map((message, index) => (
              <li key={`${index}-${message}`}>{message}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("smart");
  const [projects, setProjects] = useState<Project[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [taskSpec, setTaskSpec] = useState<TaskSpec | null>(null);
  const [generatedQueries, setGeneratedQueries] = useState<string[]>([]);
  const [searchStats, setSearchStats] = useState({ candidates: 0, analyzed: 0 });
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState("");
  const [validations, setValidations] = useState<Record<string, ValidationState>>({});

  function selectMode(mode: SearchMode) {
    setSearchMode(mode);
    setProjects([]);
    setRecommendations([]);
    setTaskSpec(null);
    setGeneratedQueries([]);
    setSearchStats({ candidates: 0, analyzed: 0 });
    setHasSearched(false);
    setError("");
    setValidations({});
  }

  async function handleSearch() {
    setIsLoading(true);
    setHasSearched(false);
    setError("");
    setProjects([]);
    setRecommendations([]);
    setTaskSpec(null);
    setGeneratedQueries([]);
    setSearchStats({ candidates: 0, analyzed: 0 });
    setValidations({});

    try {
      const endpoint = searchMode === "direct"
        ? "/search"
        : searchMode === "recommend" ? "/recommend-search" : "/smart-search";
      const response = await fetch(`${apiBaseUrl}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });

      if (!response.ok) {
        const errorDetails = await response.text();
        throw new Error(
          `Search request failed (${response.status}): ${errorDetails || response.statusText}`,
        );
      }

      if (searchMode === "direct") {
        const responseData = (await response.json()) as Project[];
        setProjects(responseData);
      } else if (searchMode === "recommend") {
        const responseData = (await response.json()) as RecommendSearchResponse;
        setRecommendations(responseData.recommendations.slice(0, 5));
        setTaskSpec(responseData.task_spec);
        setGeneratedQueries(responseData.generated_queries);
        setSearchStats({
          candidates: responseData.candidate_count,
          analyzed: responseData.analyzed_count,
        });
      } else {
        const responseData = (await response.json()) as SmartSearchResponse;
        setProjects(responseData.repositories);
        setTaskSpec(responseData.task_spec);
        setGeneratedQueries(responseData.generated_queries);
      }
      setHasSearched(true);
    } catch (caughtError) {
      console.error("Search request failed:", caughtError);
      setProjects([]);
      setRecommendations([]);
      setTaskSpec(null);
      setGeneratedQueries([]);
      setSearchStats({ candidates: 0, analyzed: 0 });
      setHasSearched(false);
      setError("搜索失败，请稍后重试。");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleValidateRepository(fullName: string) {
    setValidations((current) => ({
      ...current,
      [fullName]: { status: "loading" },
    }));

    try {
      const response = await fetch(`${apiBaseUrl}/validate-repository`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: fullName }),
      });

      if (!response.ok) {
        const errorDetails = await response.text();
        throw new Error(
          `Validation request failed (${response.status}): ${errorDetails || response.statusText}`,
        );
      }

      const report = (await response.json()) as RuntimeReport;
      setValidations((current) => ({
        ...current,
        [fullName]: { status: "complete", report },
      }));
    } catch (caughtError) {
      console.error("Repository validation failed:", caughtError);
      setValidations((current) => ({
        ...current,
        [fullName]: {
          status: "error",
          message: "验证失败，请稍后重试。",
        },
      }));
    }
  }

  const resultCount = searchMode === "recommend" ? recommendations.length : projects.length;
  const isAnyValidationLoading = Object.values(validations).some(
    (validation) => validation.status === "loading",
  );

  return (
    <main>
      <section className="search-panel">
        <header className="page-header">
          <h1>GitHub Task Search</h1>
          <div className="mode-switch" role="group" aria-label="搜索模式">
            <button
              className={searchMode === "direct" ? "mode-button active" : "mode-button"}
              type="button"
              aria-pressed={searchMode === "direct"}
              onClick={() => selectMode("direct")}
              disabled={isLoading}
            >
              直接搜索
            </button>
            <button
              className={searchMode === "smart" ? "mode-button active" : "mode-button"}
              type="button"
              aria-pressed={searchMode === "smart"}
              onClick={() => selectMode("smart")}
              disabled={isLoading}
            >
              智能搜索
            </button>
            <button
              className={searchMode === "recommend" ? "mode-button active" : "mode-button"}
              type="button"
              aria-pressed={searchMode === "recommend"}
              onClick={() => selectMode("recommend")}
              disabled={isLoading}
            >
              深度推荐
            </button>
          </div>
        </header>

        <textarea
          aria-label="项目需求描述"
          placeholder={placeholder}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          rows={6}
        />
        <button className="search-button" type="button" onClick={handleSearch} disabled={isLoading}>
          {isLoading
            ? searchMode === "recommend" ? "分析中…" : "正在搜索 GitHub..."
            : searchMode === "recommend" ? "深度推荐搜索" : searchMode === "direct" ? "搜索 GitHub" : "智能搜索"}
        </button>

        {isLoading && (
          <div className="loading-status" role="status" aria-live="polite">
            <strong>
              {searchMode === "recommend" ? "正在分析 GitHub 项目，" : "正在搜索 GitHub..."}
            </strong>
            {searchMode === "recommend" && <span>这可能需要一些时间……</span>}
          </div>
        )}
        {error && <p className="search-error" role="alert">{error}</p>}

        {taskSpec && (
          <section className="search-context" aria-label="智能搜索上下文">
            <div className="task-understanding">
              <h2>AI理解到的任务</h2>
              <dl className="task-spec">
                <div>
                  <dt>task</dt>
                  <dd>{taskSpec.task || "未指定"}</dd>
                </div>
                <div>
                  <dt>domain</dt>
                  <dd>{formatValues(taskSpec.domain)}</dd>
                </div>
                <div>
                  <dt>framework</dt>
                  <dd>{formatValues(taskSpec.framework)}</dd>
                </div>
                <div>
                  <dt>hardware</dt>
                  <dd>{formatValues(taskSpec.hardware)}</dd>
                </div>
                <div>
                  <dt>must_have</dt>
                  <dd>{formatValues(taskSpec.must_have)}</dd>
                </div>
                <div>
                  <dt>preferences</dt>
                  <dd>{formatValues(taskSpec.preferences)}</dd>
                </div>
              </dl>
            </div>
            <div className="generated-query-section">
              <h2>自动生成的搜索词</h2>
              {generatedQueries.length > 0 ? (
                <ol className="generated-query-list">
                  {generatedQueries.map((generatedQuery) => (
                    <li key={generatedQuery}>{generatedQuery}</li>
                  ))}
                </ol>
              ) : (
                <p className="empty-generated-queries">未生成搜索词</p>
              )}
            </div>
          </section>
        )}

        {hasSearched && !isLoading && resultCount === 0 && (
          <p className="empty-results" role="status">
            未找到相关 GitHub 项目
          </p>
        )}

        {projects.length > 0 && (searchMode === "smart" || searchMode === "direct") && (
          <section className="results" aria-label="搜索结果">
            <h2>{searchMode === "direct" ? "GitHub 搜索结果" : "智能搜索结果"}</h2>
            <div className="result-list">
              {projects.map((project) => (
                <article className="result-item" key={project.full_name}>
                  <div className="result-heading">
                    <h3>{project.full_name}</h3>
                  </div>
                  <p className="result-description">
                    {project.description || "暂无项目描述"}
                  </p>
                  <dl className="result-meta">
                    {project.preliminary_score !== undefined && (
                      <div>
                        <dt>初步匹配分数</dt>
                        <dd>{project.preliminary_score}</dd>
                      </div>
                    )}
                    <div>
                      <dt>Stars</dt>
                      <dd>{project.stars.toLocaleString()}</dd>
                    </div>
                    <div>
                      <dt>语言</dt>
                      <dd>{project.language || "未标注"}</dd>
                    </div>
                    <div>
                      <dt>更新时间</dt>
                      <dd>
                        <time dateTime={project.updated_at}>
                          {new Date(project.updated_at).toLocaleString("zh-CN")}
                        </time>
                      </dd>
                    </div>
                  </dl>
                  <a
                    className="github-link"
                    href={project.html_url}
                    target="_blank"
                    rel="noreferrer"
                  >查看 GitHub</a>
                </article>
              ))}
            </div>
          </section>
        )}

        {recommendations.length > 0 && searchMode === "recommend" && (
          <section className="recommendations" aria-label="深度推荐结果">
            <div className="recommendations-heading">
              <div>
                <p className="section-kicker">DEEP RECOMMENDATIONS</p>
                <h2>Top 5 GitHub 项目</h2>
              </div>
              <p className="analysis-count">
                候选 {searchStats.candidates} · 已分析 {searchStats.analyzed}
              </p>
            </div>

            <div className="recommendation-list">
              {recommendations.map((recommendation) => {
                const validation = validations[recommendation.full_name];
                return (
                <article className="recommendation-card" key={recommendation.full_name}>
                  <header className="recommendation-header">
                    <div className="rank" aria-label={`排名 ${recommendation.rank}`}>
                      <span>#{recommendation.rank}</span>
                    </div>
                    <div className="repository-title">
                      <h3>{recommendation.full_name}</h3>
                      <p>{recommendation.description || "暂无项目描述"}</p>
                    </div>
                    <div className="final-score" aria-label={`综合评分 ${recommendation.final_score}`}>
                      <strong>{recommendation.final_score}</strong>
                      <span>综合评分</span>
                    </div>
                  </header>

                  <dl className="repository-meta">
                    <div>
                      <dt>Stars</dt>
                      <dd>{recommendation.stars.toLocaleString()}</dd>
                    </div>
                    <div>
                      <dt>语言</dt>
                      <dd>{recommendation.language || "未标注"}</dd>
                    </div>
                  </dl>

                  <section className="score-section" aria-label="评分明细">
                    <h4>评分明细</h4>
                    <div className="score-grid">
                      <ScoreItem label="任务匹配度" value={recommendation.score_breakdown.task_match} max={30} />
                      <ScoreItem label="完整性" value={recommendation.score_breakdown.completeness} max={20} />
                      <ScoreItem label="必须条件满足度" value={recommendation.score_breakdown.must_have} max={20} />
                      <ScoreItem label="维护情况" value={recommendation.score_breakdown.maintenance} max={10} />
                      <ScoreItem label="文档质量" value={recommendation.score_breakdown.documentation} max={10} />
                      <ScoreItem label="社区指标" value={recommendation.score_breakdown.community} max={5} />
                      <ScoreItem label="环境完整性" value={recommendation.score_breakdown.environment} max={5} />
                    </div>
                  </section>

                  <section className="profile-section" aria-label="项目分析摘要">
                    <h4>项目分析</h4>
                    <dl className="profile-grid">
                      <div>
                        <dt>任务</dt>
                        <dd>{formatValues(recommendation.repo_profile?.tasks ?? [])}</dd>
                      </div>
                      <div>
                        <dt>领域</dt>
                        <dd>{formatValues(recommendation.repo_profile?.domains ?? [])}</dd>
                      </div>
                      <div>
                        <dt>框架</dt>
                        <dd>{formatProfileValue(recommendation.repo_profile?.framework)}</dd>
                      </div>
                      <div>
                        <dt>训练代码</dt>
                        <dd>{formatProfileBoolean(recommendation.repo_profile?.has_training_code)}</dd>
                      </div>
                      <div>
                        <dt>训练入口</dt>
                        <dd>{formatProfileValue(recommendation.repo_profile?.training_entry)}</dd>
                      </div>
                      <div>
                        <dt>自定义数据集</dt>
                        <dd>{formatProfileBoolean(recommendation.repo_profile?.has_custom_dataset_support)}</dd>
                      </div>
                      <div>
                        <dt>预训练权重</dt>
                        <dd>{formatProfileBoolean(recommendation.repo_profile?.has_pretrained_weights)}</dd>
                      </div>
                      <div>
                        <dt>文档质量</dt>
                        <dd>{formatProfileValue(recommendation.repo_profile?.documentation_quality)}</dd>
                      </div>
                      <div>
                        <dt>硬件说明</dt>
                        <dd>{formatProfileValue(recommendation.repo_profile?.hardware_notes)}</dd>
                      </div>
                      <div>
                        <dt>维护说明</dt>
                        <dd>{formatProfileValue(recommendation.repo_profile?.maintenance_notes)}</dd>
                      </div>
                    </dl>
                  </section>

                  <div className="assessment-grid">
                    <section className="assessment strengths" aria-label="项目优点">
                      <h4>优点</h4>
                      {recommendation.strengths.length > 0 ? (
                        <ul>
                          {recommendation.strengths.map((strength) => <li key={strength}>{strength}</li>)}
                        </ul>
                      ) : <p>暂无可靠结论</p>}
                    </section>
                    <section className="assessment weaknesses" aria-label="项目缺点">
                      <h4>缺点</h4>
                      {recommendation.weaknesses.length > 0 ? (
                        <ul>
                          {recommendation.weaknesses.map((weakness) => <li key={weakness}>{weakness}</li>)}
                        </ul>
                      ) : <p>暂无可靠结论</p>}
                    </section>
                  </div>

                  <section className="evidence-section" aria-label="关键证据">
                    <h4>关键证据</h4>
                    <div className="evidence-list">
                      {Object.entries(recommendation.evidence).map(([conclusion, evidence]) => (
                        <div className="evidence-row" key={conclusion}>
                          <strong>{evidenceLabels[conclusion] || conclusion}</strong>
                          <code>{evidence.source || "unknown"}</code>
                          <span>{evidence.reason || "暂无可靠证据"}</span>
                        </div>
                      ))}
                    </div>
                  </section>

                  {validation && <RuntimeValidationPanel state={validation} />}

                  <div className="recommendation-actions">
                    <button
                      className="validate-button"
                      type="button"
                      onClick={() => handleValidateRepository(recommendation.full_name)}
                      disabled={isAnyValidationLoading}
                    >
                      {validation?.status === "loading" ? "验证中…" : "验证可运行性"}
                    </button>
                    <a
                      className="github-link"
                      href={recommendation.html_url}
                      target="_blank"
                      rel="noreferrer"
                    >查看 GitHub</a>
                  </div>
                </article>
                );
              })}
            </div>
          </section>
        )}
      </section>
    </main>
  );
}

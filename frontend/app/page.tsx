"use client";

import { useState } from "react";

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

const placeholder = "描述你想寻找的 GitHub 项目，例如：找一个适合无人机语义分割的项目";
const apiBaseUrl = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

function formatValues(values: string[]) {
  return values.length > 0 ? values.join("、") : "未指定";
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [taskSpec, setTaskSpec] = useState<TaskSpec | null>(null);
  const [generatedQueries, setGeneratedQueries] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState("");

  async function handleSearch() {
    setIsLoading(true);
    setHasSearched(false);
    setError("");
    setProjects([]);
    setTaskSpec(null);
    setGeneratedQueries([]);

    try {
      const response = await fetch(`${apiBaseUrl}/smart-search`, {
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

      const responseData = (await response.json()) as SmartSearchResponse;
      setProjects(responseData.repositories);
      setTaskSpec(responseData.task_spec);
      setGeneratedQueries(responseData.generated_queries);
      setHasSearched(true);
    } catch (caughtError) {
      console.error("Search request failed:", caughtError);
      setProjects([]);
      setTaskSpec(null);
      setGeneratedQueries([]);
      setHasSearched(false);
      setError("搜索失败，请稍后重试。");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main>
      <section className="search-panel">
        <h1>GitHub Task Search</h1>
        <textarea
          aria-label="项目需求描述"
          placeholder={placeholder}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          rows={6}
        />
        <button type="button" onClick={handleSearch} disabled={isLoading}>
          {isLoading ? "正在搜索 GitHub..." : "智能搜索"}
        </button>
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
        {hasSearched && !isLoading && projects.length === 0 && (
          <p className="empty-results" role="status">
            未找到相关 GitHub 项目
          </p>
        )}
        {projects.length > 0 && (
          <section className="results" aria-label="搜索结果">
            <h2>搜索结果</h2>
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
      </section>
    </main>
  );
}

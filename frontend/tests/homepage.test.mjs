import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("the homepage displays the product title", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(source, /<h1>GitHub Task Search<\/h1>/);
});

test("the homepage displays the search controls", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(source, /<textarea/);
  assert.match(
    source,
    /const placeholder = "描述你想寻找的 GitHub 项目，例如：找一个适合无人机语义分割的项目"/,
  );
  assert.match(source, /placeholder=\{placeholder\}/);
  assert.match(source, /"智能搜索"/);
});

test("the homepage submits the query and renders search results", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(source, /^"use client";/);
  assert.match(
    source,
    /process\.env\.NEXT_PUBLIC_API_BASE_URL \?\?/,
  );
  assert.match(source, /"\/smart-search"/);
  assert.match(source, /fetch\(`\$\{apiBaseUrl\}\$\{endpoint\}`/);
  assert.doesNotMatch(
    source,
    /fetch\("http:\/\/127\.0\.0\.1:8000\/smart-search"/,
  );
  assert.match(source, /body: JSON\.stringify\(\{ query \}\)/);
  assert.match(source, /type SmartSearchResponse =/);
  assert.match(source, /responseData\.repositories/);
  assert.match(source, /responseData\.task_spec/);
  assert.match(source, /responseData\.generated_queries/);
  assert.match(source, /projects\.map/);
  assert.match(source, /project\.full_name/);
  assert.match(source, /project\.description/);
  assert.match(source, /project\.stars/);
  assert.match(source, /project\.language/);
  assert.match(source, /project\.updated_at/);
  assert.match(source, /href=\{project\.html_url\}/);
  assert.match(source, /target="_blank"/);
  assert.match(source, />查看 GitHub<\/a>/);
  assert.doesNotMatch(source, /project\.score/);
});

test("the homepage uses the Vercel same-origin backend fallback", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(source, /process\.env\.VERCEL \? "\/api\/backend"/);
});

test("the homepage renders AI understanding and generated queries", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(source, /AI理解到的任务/);
  assert.match(source, /自动生成的搜索词/);
  assert.match(source, /<dt>task<\/dt>/);
  assert.match(source, /<dt>domain<\/dt>/);
  assert.match(source, /<dt>framework<\/dt>/);
  assert.match(source, /<dt>hardware<\/dt>/);
  assert.match(source, /<dt>must_have<\/dt>/);
  assert.match(source, /<dt>preferences<\/dt>/);
  assert.match(source, /generatedQueries\.map/);
  assert.match(source, /未指定/);
  assert.match(source, /未生成搜索词/);
});

test("the homepage shows loading and empty result states", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(source, /disabled=\{isLoading\}/);
  assert.match(source, /"正在搜索 GitHub\.\.\."/);
  assert.match(source, /setIsLoading\(false\)/);
  assert.match(source, /未找到相关 GitHub 项目/);
});

test("the homepage shows a safe error and logs diagnostic details", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(source, /const errorDetails = await response\.text\(\)/);
  assert.match(source, /response\.status/);
  assert.match(source, /catch \(caughtError\)/);
  assert.match(source, /console\.error\("Search request failed:", caughtError\)/);
  assert.match(source, /setError\("搜索失败，请稍后重试。"\)/);
});

test("the homepage supports deep recommendations and renders the Top 5 details", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

  assert.match(source, /type RecommendSearchResponse =/);
  assert.match(source, /"recommend"/);
  assert.match(source, /深度推荐/);
  assert.match(source, /\/recommend-search/);
  assert.match(source, /responseData\.recommendations/);
  assert.match(source, /正在分析 GitHub 项目，/);
  assert.match(source, /这可能需要一些时间……/);
  assert.match(source, /recommendation\.rank/);
  assert.match(source, /recommendation\.full_name/);
  assert.match(source, /recommendation\.final_score/);
  assert.match(source, /recommendation\.description/);
  assert.match(source, /recommendation\.stars/);
  assert.match(source, /recommendation\.language/);
  assert.match(source, /score_breakdown\.task_match/);
  assert.match(source, /score_breakdown\.completeness/);
  assert.match(source, /score_breakdown\.must_have/);
  assert.match(source, /score_breakdown\.maintenance/);
  assert.match(source, /score_breakdown\.documentation/);
  assert.match(source, /recommendation\.strengths/);
  assert.match(source, /recommendation\.weaknesses/);
  assert.match(source, /recommendation\.evidence/);
  assert.match(source, /href=\{recommendation\.html_url\}/);
});

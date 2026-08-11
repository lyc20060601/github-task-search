from github_client import GitHubSearchError, search_repositories


def main() -> None:
    try:
        repositories = search_repositories("semantic segmentation")
    except GitHubSearchError as exc:
        raise SystemExit(f"Search failed: {exc}") from exc

    for index, repository in enumerate(repositories[:5], start=1):
        print(f"{index}. {repository['full_name']}")
        print(f"   stars: {repository['stars']}")
        print(f"   language: {repository['language']}")
        print(f"   html_url: {repository['html_url']}")


if __name__ == "__main__":
    main()

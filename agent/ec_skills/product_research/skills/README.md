Versioned copies of the two app skills that run this crawler (ProductResearchCoordinator,
ProductCrawler1-4). The app loads them from `my_skills/` (gitignored); copy a folder there to
install it. They are kept here, not in `resource/my_skills/`, because skills there are loaded as
built-in read-only skills that take precedence over the DB ones.

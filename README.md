# scryops

An independent publication on modern observability engineering — trends, deep dives, how-tos, and open questions.

## Stack

- [Hugo](https://gohugo.io/) static site generator
- Custom `scryops` theme
- [Commit Mono](https://commitmono.com/) + [Press Start 2P](https://fonts.google.com/specimen/Press+Start+2P) fonts
- Hosted at [scryops.dev](https://scryops.dev)

## Local development

```sh
hugo server -D
```

Site will be available at `http://localhost:1313/`.

## Project structure

```
content/         # Markdown content (articles, guides, howtos, qa, about)
layouts/         # Project-level layout overrides
themes/scryops/  # Custom theme (layouts, partials, CSS, icons)
static/          # Static assets copied to site root
hugo.toml        # Site configuration
```

## License

All content is copyright scryops. Theme and code are MIT unless otherwise noted.

from django.urls import include, path

# A host embedding the admin (docs/embedding-admin.md): escalated.embed_urls
# at the site root, in place of path("support/", include("escalated.urls")).
urlpatterns = [
    path("", include("escalated.embed_urls")),
]

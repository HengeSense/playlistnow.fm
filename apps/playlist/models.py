from django.db import models
from django.db.models import signals
from django.utils.translation import ugettext as _
from django.core import urlresolvers
from django.template import defaultfilters

from tagging.fields import TagField

class PlaylistCategory(models.Model):
    title = models.CharField(max_length=100, verbose_name=_(u'title'))
    parent = models.ForeignKey('PlaylistCategory', verbose_name=_(u'parent'), null=True, blank=True, related_name='children')

    class Meta:
        ordering = ('title',)

    def __unicode__(self):
        return self.title

class PlaylistTrack(models.Model):
    creation_datetime = models.DateTimeField(verbose_name=_(u'published'), auto_now_add=True)
    play_counter = models.IntegerField(verbose_name=_(u'played'), default=0)

    track = models.ForeignKey('music.track', verbose_name=_(u'track'), null=True, blank=True)
    
    title = models.CharField(max_length=100, verbose_name=_(u'title'))
    source_url = models.URLField(verbose_name=_(u'URL of the track'), null=True, blank=True)

    def __unicode__(self):
        return self.title

    class Meta:
        ordering = ('title',)

class Playlist(models.Model):
    tracks = models.ManyToManyField(PlaylistTrack, verbose_name=_(u'tracks'), null=True, blank=True)
    category = models.ForeignKey(PlaylistCategory, verbose_name=_(u'category'), null=True, blank=True)
    play_counter = models.IntegerField(verbose_name=_(u'played'), default=0)
    
    creation_user = models.ForeignKey('auth.user', verbose_name=_(u'creator'))
    creation_datetime = models.DateTimeField(verbose_name=_(u'published'), auto_now_add=True)
    modification_datetime = models.DateField(verbose_name=_(u'modified'), auto_now=True)

    title = models.CharField(max_length=100, verbose_name=_(u'title'))
    slug = models.CharField(max_length=100, verbose_name=_(u'slug'), null=True, blank=True)
    image = models.ImageField(verbose_name=_(u'icon'), null=True, blank=True, upload_to='playlist_images')

    tags = TagField()

    def __unicode__(self):
        return self.title

    class Meta:
        ordering = ('title',)

    def get_absolute_url(self):
        return urlresolvers.reverse('playlist_details', args=(self.slug,))

def autoslug(sender, instance, **kwargs):
    if not hasattr(instance, 'slug'):
        return True

    if hasattr(instance, 'name'):
        instance.slug = defaultfilters.slugify(instance.name)
    elif hasattr(instance, 'title'):
        instance.slug = defaultfilters.slugify(instance.title)

    while instance.__class__.objects.filter(slug=instance.slug).count():
        instance.slug += '-'

signals.pre_save.connect(autoslug)
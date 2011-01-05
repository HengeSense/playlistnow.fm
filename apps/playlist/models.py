from django.db import models
from django.db.models import signals
from django.db.models import Q
from django.utils.translation import ugettext as _
from django.core import urlresolvers
from django.template import defaultfilters

from tagging.fields import TagField

class PlaylistProfile(models.Model):
    user = models.OneToOneField('auth.User', verbose_name=_(u'user'))
    favorite_playlist = models.ForeignKey('Playlist')

    def get_absolute_url(self):
        return urlresolvers.reverse('user_details', args=(self.user.username,))

def autoprofile(sender, instance, **kwargs):
    try:
        instance.playlistprofile
    except PlaylistProfile.DoesNotExist:
        favorite_playlist = Playlist(
            name='virtual:favorite',
            creation_user=instance
        )
        favorite_playlist.save()

        instance.playlistprofile = PlaylistProfile(
            user=instance,
            favorite_playlist=favorite_playlist
        )
        instance.playlistprofile.save()
signals.post_save.connect(autoprofile, sender=models.get_model('auth','user'))

class PlaylistCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name=_(u'name'))
    parent = models.ForeignKey('PlaylistCategory', verbose_name=_(u'parent'), null=True, blank=True, related_name='children')
    slug = models.CharField(max_length=100, verbose_name=_(u'slug'), null=True, blank=True)

    class Meta:
        ordering = ('name',)

    def __unicode__(self):
        return self.name

    def get_absolute_url(self):
        try:
            return urlresolvers.reverse('playlist_category_details_with_parent', 
                args=(self.parent.slug, self.slug,))
        except PlaylistCategory.DoesNotExist:
            return urlresolvers.reverse('playlist_category_details', 
                args=(self.slug,))

class PlaylistModification(models.Model):
    ACTIONS = (
        ('add', _('add')),
        ('rm', _('remove')),
    )

    playlist = models.ForeignKey('Playlist')
    track = models.ForeignKey('music.Track')
    creation_user = models.ForeignKey('auth.User', verbose_name=_(u'creator'))
    creation_datetime = models.DateTimeField(verbose_name=_(u'published'), auto_now_add=True)
    action = models.CharField(max_length=3, choices=ACTIONS)

    class Meta:
        ordering = ('creation_datetime',)

    def __unicode__(self):
        return u'proposal: %s track %s to %s, by %s' % (
            self.get_action_display(),
            self.track,
            self.playlist,
            self.creation_user
        )

class Playlist(models.Model):
    tracks = models.ManyToManyField('music.Track', verbose_name=_(u'tracks'), null=True, blank=True)
    category = models.ForeignKey(PlaylistCategory, verbose_name=_(u'category'), null=True, blank=True)
    play_counter = models.IntegerField(verbose_name=_(u'played'), default=0)
    
    creation_user = models.ForeignKey('auth.User', verbose_name=_(u'creator'))
    creation_datetime = models.DateTimeField(verbose_name=_(u'published'), auto_now_add=True)
    modification_datetime = models.DateField(verbose_name=_(u'modified'), auto_now=True)

    name = models.CharField(max_length=100, verbose_name=_(u'name'))
    slug = models.CharField(max_length=100, verbose_name=_(u'slug'))
    image = models.ImageField(verbose_name=_(u'icon'), null=True, blank=True, upload_to='playlist_images')

    unique_autoslug = False

    tags = TagField()

    def __unicode__(self):
        return u'I am %s' % self.name

    class Meta:
        ordering = ('name',)

    def get_absolute_url(self):
        return urlresolvers.reverse('playlist_details', args=(
            self.creation_user.username, self.slug,))

    def to_dict(self, with_tracks=True, with_tracks_artist=True,
        with_tracks_youtube_best_id=True, for_user=None):
        data = {}
        data['object'] = {
            'name': self.name,
            'url': self.get_absolute_url(),
            'pk': self.pk,
        }
        data['tracks'] = []

        if with_tracks:
            if for_user:
                tracks = self.all_user_tracks(for_user).select_related()
            else:
                tracks = self.tracks.select_related()

            for track in tracks:
                data['tracks'].append(track.to_dict(
                    with_artist=with_tracks_artist,
                    with_youtube_best_id=with_tracks_youtube_best_id
                ))

        return data

    def added_user_tracks(self, user):
        return self.__class__.tracks.field.rel.to.objects.filter(self.added_user_tracks_condition(user))

    def added_user_tracks_condition(self, user):
        return Q(playlistmodification__playlist=self) & Q(playlistmodification__creation_user=user) & Q(playlistmodification__action='add')

    def removed_user_tracks(self, user):
        return self.__class__.tracks.field.rel.to.objects.filter(self.removed_user_tracks_condition(user))

    def removed_user_tracks_condition(self, user):
        return Q(playlistmodification__playlist=self) & Q(playlistmodification__creation_user=user) & Q(playlistmodification__action='rm')

    def all_user_tracks(self, user):
        return self.__class__.tracks.field.rel.to.objects.filter(
            (
                Q(playlist=self) | 
                self.added_user_tracks_condition(user)
            ) & ~self.removed_user_tracks_condition(user)
        ).distinct()

def autoslug(sender, instance, **kwargs):
    if not hasattr(instance, 'slug'):
        return True
    
    if not getattr(instance.__class__, 'autoslug', True):
        return True

    if hasattr(instance, 'name'):
        instance.slug = defaultfilters.slugify(instance.name)
    elif hasattr(instance, 'name'):
        instance.slug = defaultfilters.slugify(instance.name)
    
    if not instance.slug:
        instance.slug = instance.pk

    if not getattr(instance.__class__, 'unique_autoslug', False):
        return True

    while instance.__class__.objects.filter(slug=instance.slug).count():
        instance.slug += '-'

signals.pre_save.connect(autoslug)

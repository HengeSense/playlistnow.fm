from operator import or_

from django.core import urlresolvers
from django import http
from django import shortcuts
from django import template
from django.db.models import get_model
from django.db import connection, transaction
from django.db.models import Q
from django.contrib.auth import decorators
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from tagging.models import Tag, TaggedItem
from actstream.models import actor_stream, user_stream, model_stream, Follow, Action
from actstream import action
from endless_pagination.decorators import page_template

from music.views import return_json
from playlist.models import Playlist
from music.models import Track, Recommendation

def group_activities(activities):
    if not activities:
        return activities

    nogroup = [
        'started following',
        #'recommends',
    ]
    previous = None
    for activity in activities:
        if hasattr(activity, 'action_object'):
            if hasattr(previous, 'action_object') and previous.action_object.__class__ == activity.action_object.__class__ and activity.verb == previous.verb:
                activity.action_object_group = previous.action_object_group
            else:
                activity.action_object_group = [activity.action_object]
            
        if previous and activity.verb == previous.verb and activity.verb not in nogroup:
            activity.open = False
            previous.close = False
            if hasattr(activity, 'action_object') and activity.action_object.__class__ == previous.action_object.__class__:
                if activity.action_object not in activity.action_object_group:
                    activity.action_object_group.append(activity.action_object)
        else:
            activity.open = True
            if previous:
                previous.close = True
        
        previous = activity

    activities[0].open = True
    activities[len(activities)-1].close = True
    return activities

def add_activity(request):
    if not request.method == 'POST':
        return http.HttpResponseForbidden()

    if 'action_object_pk' in request.POST.keys():
        action_object = shortcuts.get_object_or_404(
            get_model(
                request.POST['action_object_app'],
                request.POST['action_object_class']
            ),
            pk=request.POST['action_object_pk']
        )
    else:
        action_object = None
    
    if 'action_object_pk' in request.POST.keys():
        action_object = shortcuts.get_object_or_404(
            get_model(
                request.POST['action_object_app'],
                request.POST['action_object_class']
            ),
            pk=request.POST['action_object_pk']
        )
    else:
        action_object = None

    action.send(
        request.user,
        request.POST['verb'],
        action_object=action_object,
        target=action_object
    )

    return http.HttpResponse('success')

def action_like(request, action_id):
    if not request.user.is_authenticated():
        return http.HttpResponseForbidden()
    try:
        object = Action.objects.get(pk=action_id)
    except Action.DoesNotExist:
        return http.HttpResponseNotFound('could not find action with id %s' % action_id)
    request.user.playlistprofile.fanof_actions.add(object)
    #action.send(request.user, verb='likes', action_object=object)
    return http.HttpResponse('action liked')

def action_unlike(request, action_id):
    if not request.user.is_authenticated():
        return http.HttpResponseForbidden()
    try:
        action = Action.objects.get(pk=action_id)
    except Action.DoesNotExist:
        return http.HttpResponseNotFound('could not find action with id %s' % action_id)
    request.user.playlistprofile.fanof_actions.remove(action)
    return http.HttpResponse('action unliked')

def action_delete(request, action_id):
    if not request.user.is_authenticated():
        return http.HttpResponseForbidden()
    try:
        action = Action.objects.get(pk=action_id)
    except Action.DoesNotExist:
        return http.HttpResponseNotFound('could not find action with id %s' % action_id)
    if action.actor != request.user:
        return http.HttpResponseForbidden('you may only delete your own actions')
    action.delete()
    return http.HttpResponse('action deleted')

def user_search_autocomplete(request, qname='query', qs=User.objects.all()):
    if not request.GET.get(qname, False):
        return return_json()

    q = request.GET[qname]

    response = {
        'query': request.GET[qname].encode('utf-8'),
        'suggestions': [],
        'data': [],
    }

    qs = qs.filter(
        Q(username__icontains=q) |
        Q(first_name__icontains=q) |
        Q(last_name__icontains=q)
    ).select_related('playlistprofile')

    for user in qs[:15]:
        response['suggestions'].append(unicode(user.playlistprofile))
        response['data'].append({
            'url': user.playlistprofile.get_absolute_url(),
            'html': '<img src="%s"> %s' % (
                user.playlistprofile.avatar_url,
                unicode(user.playlistprofile),
            )
        })

    return return_json(response)

def friends_search_autocomplete(request, qname='query'):
    if not request.user.is_authenticated():
        return http.HttpResponseForbidden()

    if not request.GET.get(qname, False):
        return return_json()

    q = request.GET[qname]
    qs = request.user.playlistprofile.friends()
    qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q))

    response = {
        'query': request.GET[qname].encode('utf-8'),
        'suggestions': [],
        'data': [],
    }

    for user in qs:
        print user
        response['suggestions'].append(unicode(user.playlistprofile))
        response['data'].append({
            'url': user.playlistprofile.get_absolute_url(),
            'html': '<img src="%s"> %s' % (
                user.playlistprofile.avatar_url,
                unicode(user.playlistprofile),
            ),
            'pk': user.pk,
        })

    return return_json(response)

def user_search(request, qname='term', qs=User.objects.all(),
    template_name='auth/user_list.html', extra_context=None):
    context = {}
    q = request.GET.get(qname, '')
    qs = qs.filter(
        Q(username__icontains=q) |
        Q(first_name__icontains=q) |
        Q(last_name__icontains=q)
    ).select_related('playlistprofile')
    context['object_list'] = qs
    context.update(extra_context or {})
    return shortcuts.render_to_response(template_name, context,
        context_instance=template.RequestContext(request))

@page_template('auth/user_activities.html')
def user_details(request, slug, tab='activities',
    template_name='auth/user_detail.html', extra_context=None):
    context = {
        'tab': tab,
    }
    
    if 'page' not in request.GET: 
        template_name = 'auth/user_detail.html'
    print template_name

    user = shortcuts.get_object_or_404(User, username=slug)
    context['user'] = user

    c = ContentType.objects.get_for_model(User)

    #follows_users_ids = Follow.objects.filter(user=user, content_type=c).exclude(object_id=user.pk).values_list('object_id', flat=True)
    #follows_qs = User.objects.filter(id__in=follows_users_ids).select_related('playlistprofile')

    follows_users_ids = Follow.objects.filter(user=user,
                                              content_type__app_label='auth',
                                              content_type__model='user') \
                                      .exclude(object_id=user.pk) \
                                      .values_list('object_id', flat=True)
    follows_qs = User.objects.filter(id__in=follows_users_ids) \
                             .select_related('playlistprofile')
    followers_qs = User.objects.filter(follow__object_id=user.pk, follow__content_type=c).select_related('playlistprofile')

    if tab == 'playlists':
        context['playlists'] = user.playlist_set.all()
    elif tab == 'activities':
        activities = Action.objects.filter(
            Q(
                actor_content_type = ContentType.objects.get_for_model(user),
                actor_object_id = user.pk
            ) | Q(
                action_object_content_type = ContentType.objects.get_for_model(Recommendation),
                action_object_object_id__in = Recommendation.objects.filter(target=user).values_list('id')
            )
        ).order_by('-timestamp')

        context['activities'] = group_activities(activities)
    elif tab == 'follows':
        context['follows_qs'] = follows_qs
    elif tab == 'followers':
        context['followers_qs'] = followers_qs

    # for the sidebar
    context['follows'] = follows_qs._clone()[:20]
    context['followers'] = followers_qs._clone()[:20]

    profiles = user.twitterprofile_set.all()
    if profiles:
        context['twitterprofile'] = profiles[0]
    profiles = user.facebookprofile_set.all()
    if profiles:
        context['facebookprofile'] = profiles[0]
    profiles = user.gfcprofile_set.all()
    if profiles:
        context['gfcprofile'] = profiles[0]

    context['ctype'] = c
    context.update(extra_context or {})
    return shortcuts.render_to_response(template_name, context,
        context_instance=template.RequestContext(request))

def tag_details(request, slug,
    template_name='tagging/tag_detail.html', extra_context=None):
    context = {}

    context['object'] = shortcuts.get_object_or_404(Tag, name=slug)
    context['object_list'] = TaggedItem.objects.get_by_model(
        Playlist, context['object'])

    context.update(extra_context or {})
    return shortcuts.render_to_response(template_name, context,
        context_instance=template.RequestContext(request))

def empty(request,
    template_name='site_base.html', extra_context=None):
    context = {
        'empty': True,
    }

    if request.user.is_authenticated():
        context['my_playlists'] = Playlist.objects.filter(creation_user=request.user)[:20]

    context.update(extra_context or {})
    return shortcuts.render_to_response(template_name, context,
        context_instance=template.RequestContext(request))

def me(request,
    template_name='me.html', extra_context=None):
    context = {}

    if not request.user.is_authenticated():
        if not 'socialregistration_profile' in request.session:
            return http.HttpResponseRedirect(urlresolvers.reverse(
                'acct_signup'))
        elif not 'socialregistration_userdata' in request.session:
            return http.HttpResponseRedirect(urlresolvers.reverse(
                'socialregistration_userdata'))
        elif not 'socialregistration_friends' in request.session:
            return http.HttpResponseRedirect(urlresolvers.reverse(
                'socialregistration_friends'))
        else:
            return http.HttpResponseRedirect(urlresolvers.reverse(
                'socialregistration_complete'))

    follows = Follow.objects.filter(user=request.user)
    print follows
    qs = [Action.objects.stream_for_actor(follow.actor) for follow in follows]

    if follows.count():
        activities = reduce(or_, qs).order_by('-timestamp')
    else:
        activities = Action.objects.none()
    print activities

    context['activities'] = group_activities(activities)

    context.update(extra_context or {})
    return shortcuts.render_to_response(template_name, context,
        context_instance=template.RequestContext(request))

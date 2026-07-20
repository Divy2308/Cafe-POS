self.addEventListener('push', event => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (e) {
    payload = {};
  }
  const title = payload.title || 'Qbite';
  const options = {
    body: payload.body || 'You have a new update.',
    icon: '/static/img/qbitecriclelogo.png',
    badge: '/static/img/qbitecriclelogo.png',
    tag: payload.tag || 'qbite-update',
    data: payload.data || {},
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification?.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      for (const client of windowClients) {
        if ('focus' in client) {
          client.focus();
          if ('navigate' in client) {
            client.navigate(url);
          }
          return client;
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
      return null;
    })
  );
});

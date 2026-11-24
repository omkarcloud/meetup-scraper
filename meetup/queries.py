"""The GraphQL operations of www.meetup.com's own pages (POST /gql2), each
with the id the page sends for it and its full text.

The site's pages send an operation by its saved id only (Apollo "persisted
query": operationName + variables + extensions.persistedQuery.sha256Hash)
and the server answers from the text it has stored under that id. An id
the server no longer knows answers HTTP 200 with
{"errors": [{"message": "PersistedQueryNotFound"}]}: fetch.py then sends
the operation's TEXT, which the server runs as it is.

Both were read from the site on 2026-11-21 (site build 49c0734f): the ids
from the calls the pages made, the texts from the page scripts (the
operation's own template plus every fragment it spreads, by name). Each
text was sent once with the page's variables and answered every key the
id's answer holds (14 of 14 operations).

When the site changes an operation, its id changes: the old id keeps
answering while the server remembers it, then the text takes over. A text
the server rejects (a field it removed) is a MeetupSchemaChanged error:
read the operation again from the page scripts.

One operation is ours, not a page's: getTopicStats. It has no saved id and
always goes out as text.
"""

EVENT_SEARCH_WITH_SERIES = """\
query eventSearchWithSeries(
    $query: String!
    $lat: Float!
    $lon: Float!
    $startDateRange: DateTime
    $endDateRange: DateTime
    $eventType: EventType
    $radius: Float
    $isHappeningNow: Boolean
    $isStartingSoon: Boolean
    $categoryId: ID
    $topicCategoryId: ID
    $city: String
    $state: String
    $country: String
    $zip: String
    $sortField: KeywordSortField
    $first: Int
    $after: String
    $numberOfEventsForSeries: Int
    $seriesStartDate: Date
    $doConsolidateEvents: Boolean
    $dataConfiguration: String
    $rsvpCountRange: RsvpCountRange
  ) {
    results: eventSearch(
      filter: {
        query: $query
        lat: $lat
        lon: $lon
        startDateRange: $startDateRange
        endDateRange: $endDateRange
        eventType: $eventType
        radius: $radius
        isHappeningNow: $isHappeningNow
        isStartingSoon: $isStartingSoon
        categoryId: $categoryId
        topicCategoryId: $topicCategoryId
        city: $city
        state: $state
        country: $country
        zip: $zip
        doConsolidateEvents: $doConsolidateEvents
        rsvpCountRange: $rsvpCountRange
      }
      first: $first
      after: $after
      sort: { sortField: $sortField }
      dataConfiguration: $dataConfiguration
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      totalCount
      edges {
        node {
          ...FindEventInfo
          group {
            isNewGroup
          }
        }
        metadata {
          recId
          recSource
        }
      }
    }
  }

fragment FindEventInfo on Event {
    id
    title
    dateTime
    description
    eventType
    eventUrl
    isAttending
    isSaved
    maxTickets
    rsvpState
    featuredEventPhoto {
      baseUrl
      highResUrl
      id
    }
    displayPhoto {
      baseUrl
      highResUrl
      id
    }
    feeSettings {
      accepts
      currency
      amount
    }
    group {
      id
      name
      urlname
      timezone
      keyGroupPhoto {
        baseUrl
        highResUrl
        id
      }
      stats {
        eventRatings {
          average
          totalRatings
        }
      }
    }
    socialProofInsights {
      isTrendingEvent
      totalInterestedUsers
      interestedUsersSample {
        memberPhoto {
          id
          source: highResUrl
          baseUrl
        }
      }
    }
    rsvps {
      totalCount
      edges {
        node {
          isHost
          user: member {
            id
            name
            memberPhoto {
              id
              source: highResUrl
              baseUrl
            }
          }
        }
      }
    }
    series {
      description
      weeklyRecurrence {
        weeklyDaysOfWeek
        weeklyInterval
      }
      monthlyRecurrence {
        monthlyDayOfWeek
        monthlyWeekOfMonth
      }
      events(numberOfEvents: $numberOfEventsForSeries, startDate: $seriesStartDate) {
        edges {
          node {
            id
            dateTime
            isAttending
            group {
              urlname
            }
          }
        }
      }
    }
    venue {
      name
      address
      city
      state
      country
    }
  }
"""

RECOMMENDED_EVENTS_WITH_SERIES = """\
query recommendedEventsWithSeries(
    $lat: Float!
    $lon: Float!
    $categoryId: ID
    $topicCategoryId: ID
    $startDateRange: String
    $endDateRange: String
    $first: Int
    $after: String
    $eventType: EventType
    $radius: Float
    $isHappeningNow: Boolean
    $isStartingSoon: Boolean
    $sortField: RecommendedEventsSortField
    $numberOfEventsForSeries: Int
    $seriesStartDate: Date
    $doConsolidateEvents: Boolean
    $doPromotePaypalEvents: Boolean
    $indexAlias: String
    $dataConfiguration: String
    $shouldInjectNgaEvents: Boolean
    $rsvpCountRange: RsvpCountRange
  ) {
    result: recommendedEvents(
      filter: {
        lat: $lat
        lon: $lon
        categoryId: $categoryId
        topicCategoryId: $topicCategoryId
        startDateRange: $startDateRange
        endDateRange: $endDateRange
        eventType: $eventType
        radius: $radius
        isHappeningNow: $isHappeningNow
        isStartingSoon: $isStartingSoon
        doConsolidateEvents: $doConsolidateEvents
        doPromotePaypalEvents: $doPromotePaypalEvents
        indexAlias: $indexAlias
        shouldInjectNgaEvents: $shouldInjectNgaEvents
        rsvpCountRange: $rsvpCountRange
      }
      first: $first
      after: $after
      sort: { sortField: $sortField }
      dataConfiguration: $dataConfiguration
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      totalCount
      edges {
        node {
          ...FindEventInfo
        }
        metadata {
          recId
          recSource
        }
      }
    }
  }

fragment FindEventInfo on Event {
    id
    title
    dateTime
    description
    eventType
    eventUrl
    isAttending
    isSaved
    maxTickets
    rsvpState
    featuredEventPhoto {
      baseUrl
      highResUrl
      id
    }
    displayPhoto {
      baseUrl
      highResUrl
      id
    }
    feeSettings {
      accepts
      currency
      amount
    }
    group {
      id
      name
      urlname
      timezone
      keyGroupPhoto {
        baseUrl
        highResUrl
        id
      }
      stats {
        eventRatings {
          average
          totalRatings
        }
      }
    }
    socialProofInsights {
      isTrendingEvent
      totalInterestedUsers
      interestedUsersSample {
        memberPhoto {
          id
          source: highResUrl
          baseUrl
        }
      }
    }
    rsvps {
      totalCount
      edges {
        node {
          isHost
          user: member {
            id
            name
            memberPhoto {
              id
              source: highResUrl
              baseUrl
            }
          }
        }
      }
    }
    series {
      description
      weeklyRecurrence {
        weeklyDaysOfWeek
        weeklyInterval
      }
      monthlyRecurrence {
        monthlyDayOfWeek
        monthlyWeekOfMonth
      }
      events(numberOfEvents: $numberOfEventsForSeries, startDate: $seriesStartDate) {
        edges {
          node {
            id
            dateTime
            isAttending
            group {
              urlname
            }
          }
        }
      }
    }
    venue {
      name
      address
      city
      state
      country
    }
  }
"""

GROUP_SEARCH = """\
query groupSearch(
    $first: Int
    $after: String
    $query: String!
    $lat: Float!
    $lon: Float!
    $radius: Float
    $categoryId: ID
    $topicCategoryId: ID
    $city: String
    $state: String
    $country: String
    $zip: String
    $dataConfiguration: String
    $frozenOnly: Boolean
  ) {
    results: groupSearch(
      first: $first
      after: $after
      filter: {
        query: $query
        lat: $lat
        lon: $lon
        radius: $radius
        categoryId: $categoryId
        topicCategoryId: $topicCategoryId
        city: $city
        state: $state
        country: $country
        zip: $zip
        frozenOnly: $frozenOnly
      }
      dataConfiguration: $dataConfiguration
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      totalCount
      edges {
        node {
          ...BuildMeetupGroupSearch
        }
        metadata {
          recId
          recSource
        }
      }
    }
  }

fragment BuildMeetupGroupSearch on Group {
    id
    name
    link
    description
    link
    city
    state
    status
    country
    isPrivate
    isNewGroup
    groupPhoto {
      id
      baseUrl
    }
    stats {
      memberCounts {
        all
      }
      eventRatings {
        average
        totalRatings
      }
    }
    sampleMembers: memberships(first: 10, filter: { status: [ACTIVE, LEADER] }) {
      edges {
        node {
          id
          name
          memberPhoto {
            id
            baseUrl
          }
        }
      }
    }
  }
"""

GET_RECOMMENDED_GROUPS = """\
query getRecommendedGroups(
    $lat: Float!
    $lon: Float!
    $categoryId: ID
    $topicCategoryId: ID
    $first: Int
    $after: String
    $radius: Int
    $visibility: GroupVisibility
    $indexAlias: String
    $frozenOnly: Boolean
    $topicsList: [ID!]
    $ignoreNewGroups: Boolean
    $boostNewGroup: Boolean
    $distanceDecayRate: Float
    $topicMatchMode: TopicMatchMode
  ) {
    results: recommendedGroups(
      filter: {
        lat: $lat
        lon: $lon
        categoryId: $categoryId
        topicCategoryId: $topicCategoryId
        radius: $radius
        visibility: $visibility
        indexAlias: $indexAlias
        frozenOnly: $frozenOnly
        topicsList: $topicsList
        boostNewGroup: $boostNewGroup
        distanceDecayRate: $distanceDecayRate
        topicMatchMode: $topicMatchMode
      }
      after: $after
      first: $first
      ignoreNewGroups: $ignoreNewGroups
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      totalCount
      edges {
        node {
          ...BuildMeetupGroupSearch
        }
        metadata {
          recId
          recSource
        }
      }
    }
  }

fragment BuildMeetupGroupSearch on Group {
    id
    name
    link
    description
    link
    city
    state
    status
    country
    isPrivate
    isNewGroup
    groupPhoto {
      id
      baseUrl
    }
    stats {
      memberCounts {
        all
      }
      eventRatings {
        average
        totalRatings
      }
    }
    sampleMembers: memberships(first: 10, filter: { status: [ACTIVE, LEADER] }) {
      edges {
        node {
          id
          name
          memberPhoto {
            id
            baseUrl
          }
        }
      }
    }
  }
"""

GROUP_HOME = """\
query groupHome($urlname: String!, $includePrivateInfo: Boolean! = true) {
    groupByUrlname(urlname: $urlname) {
      ...GroupHomeHeaderData
      description
      video {
        provider
        url
      }
      ...GroupHomeFutureEvents
      pastEvents: events(filter: { status: [PAST] }, sort: DESC, first: 4) {
        totalCount
        edges {
          node {
            ...CoreGroupHomeEventPublic
          }
        }
      }
      activeTopics {
        id
        name
        urlkey
      }
      topicCategory {
        id
        name
        urlkey
      }
      sponsors {
        edges {
          node {
            id
            name
            description
            url
            logoPhoto {
              id
              standardUrl
            }
          }
        }
      }
      foundedDate
      socialNetworks {
        identifier
        url
        service
      }
      canSeeMemberList @include(if: $includePrivateInfo)
      memberships(first: 17, filter: { status: [ACTIVE, LEADER] }) {
        edges {
          node {
            id
            name
            memberPhoto {
              id
              source: highResUrl
            }
          }
        }
      }
      stepUpInfo {
        organizerNominees {
          id
        }
      }
    }
  }

fragment GroupHomeHeaderData on Group {
    id
    name
    urlname
    timezone
    isPrivate
    organizer {
      id
      name
      email
      memberPhoto {
        id
        source: highResUrl
      }
      isStarterOrganizer @include(if: $includePrivateInfo)
      isSuperOrganizer
    }
    stats {
      memberCounts {
        all
        leadership
        pending
      }
      eventRatings {
        average
        total
      }
    }
    lat
    lon
    joinMode
    isMember @include(if: $includePrivateInfo)
    status
    city
    state
    country
    groupPhoto: keyGroupPhoto {
      id
      source: highResUrl
    }
    proNetwork {
      id
      urlname
      name
      logo {
        id
        source: highResUrl
      }
      groups {
        totalCount
      }
    }
    isPrimaryOrganizer
    canSeeMemberList @include(if: $includePrivateInfo)
    membershipMetadata @include(if: $includePrivateInfo) {
      status
      role
      dues {
        status
        trialEndDate
        paidEndDate
        graceEndDate
      }
      preferences(names: ["member_connection_availability"]) {
        name
        value
      }
    }
    draftEvents: events(filter: { status: [DRAFT] }, first: 1) {
      totalCount
    }
    needsQuestions
    needsPhoto
    questions {
      id
      question
      sort
    }
    memberDuesSettingsUrl
    duesSettings {
      amount
      paymentType
      currency
      interval
      feeDescription
      trialPeriodDays
    }
    canAddPhotos @include(if: $includePrivateInfo)
    calendarFeeds {
      rss
      ical
      icalWeb
      rsvpRss
    }
    welcomeBlurb
    organizerStartTime
    leaders: memberships(filter: { status: LEADER }, first: 50) {
      edges {
        node {
          id
          name
          isSuperOrganizer
        }
      }
    }
  }

fragment GroupHomeFutureEvents on Group {
    featuredEvent {
      ...CoreGroupHomeEventPublic
    }
    upcomingEvents: events(filter: { status: [ACTIVE] }, sort: ASC, first: 4) {
      totalCount
      edges {
        node {
          ...CoreGroupHomeEventPublic
        }
      }
    }
  }

fragment CoreGroupHomeEventPublic on Event {
    id
    title
    eventUrl
    description
    isSaved
    group {
      id
      name
      timezone
      keyGroupPhoto {
        id
        baseUrl
        highResUrl
      }
    }
    creatorMember {
      id
    }
    eventHosts {
      memberId
    }
    feeSettings {
      accepts
      currency
      amount
    }
    venue {
      id
      name
      address
      city
      state
      country
    }
    dateTime
    createdTime
    endTime
    going {
      totalCount
    }
    isAttending @include(if: $includePrivateInfo)
    isOnline
    eventType
    status
    series {
      __typename
      description
      weeklyRecurrence {
        weeklyDaysOfWeek
        weeklyInterval
      }
      monthlyRecurrence {
        monthlyDayOfWeek
        monthlyWeekOfMonth
      }
    }
    featuredEventPhoto {
      id
      baseUrl
      highResUrl
    }
    displayPhoto {
      id
      baseUrl
      highResUrl
    }
    rsvpState @include(if: $includePrivateInfo)
    rsvps(first: 5) {
      totalCount
      edges {
        node {
          id
          member {
            id
            name
            memberPhoto {
              id
              source: highResUrl
            }
          }
        }
      }
    }
    maxTickets
    actions @include(if: $includePrivateInfo)
    rsvpSettings {
      rsvpsClosed
    }
    isNetworkEvent
    networkEvent {
      rsvpCount
      groupCount
    }
    socialLabels
    socialProofInsights {
      ...SocialProofInsightsForGroupHome
    }
  }

fragment SocialProofInsightsForGroupHome on SocialProofInsights {
    isTrendingEvent
    totalInterestedUsers
    interestedUsersSample {
      memberPhoto {
        id
        baseUrl
        highResUrl
      }
    }
  }
"""

GET_GROUP_FEEDBACK_INFO = """\
query getGroupFeedbackInfo($groupUrlname: String!, $first: Int) {
    groupByUrlname(urlname: $groupUrlname) {
      ...GroupFeedbackInfo
    }
  }

fragment GroupFeedbackInfo on Group {
    id
    urlname
    groupPhoto {
      id
      baseUrl
    }
    name
    country
    city
    state
    stats {
      eventRatings {
        average
        totalReviews
        totalRatings
        breakdown {
          count
          rating
        }
        details {
          membersWouldAttendAgain
          membersDisliked {
            count
            topic
          }
          membersLiked {
            count
            topic
          }
        }
      }
    }
    pastEvents: events(filter: { status: [PAST] }, sort: DESC, first: 3) {
      totalCount
      edges {
        node {
          id
          title
          eventUrl
          dateTime
          displayPhoto {
            id
            source: highResUrl
            baseUrl
          }
          feedbackSurvey {
            attributes {
              count
              answerId
            }
            totalCount
            totalComments
            membersWouldAttendAgain
            averageRating
            totalReviews
            totalRatings
          }
        }
      }
    }
    eventReviews(first: $first, sort: { sortField: CREATE_DATE, sortOrder: DESC }) {
      totalCount
      edges {
        node {
          responseId
          member {
            id
            name
            memberPhoto {
              id
              baseUrl
            }
          }
          event {
            id
            title
            eventUrl
          }
          rating
          createDate
          comment
          freeTextFeedback
          reply {
            eventReviewReplyId
            createdDate
            member {
              id
              name
              memberPhoto {
                id
                baseUrl
              }
            }
            replyText
          }
          details {
            membersLiked {
              topic
            }
            membersDisliked {
              topic
            }
          }
        }
      }
    }
  }
"""

GET_UPCOMING_GROUP_EVENTS = """\
query getUpcomingGroupEvents(
    $urlname: String!
    $after: String
    $afterDateTime: DateTime
    $beforeDateTime: DateTime
    $title: String
  ) {
    groupByUrlname(urlname: $urlname) {
      id
      organizer {
        id
        isStarterOrganizer
      }
      events(
        filter: {
          status: [ACTIVE, PAST, CANCELLED]
          afterDateTime: $afterDateTime
          beforeDateTime: $beforeDateTime
          title: $title
        }
        sort: ASC
        first: 30
        after: $after
      ) {
        totalCount
        pageInfo {
          endCursor
          hasNextPage
        }
        edges {
          node {
            ...CoreGroupHomeEvent
          }
        }
      }
    }
  }

fragment CoreGroupHomeEvent on Event {
    id
    title
    eventUrl
    description
    isSaved
    group {
      id
      name
      timezone
      keyGroupPhoto {
        id
        baseUrl
        highResUrl
      }
    }
    creatorMember {
      id
    }
    eventHosts {
      memberId
    }
    feeSettings {
      accepts
      currency
      amount
    }
    venue {
      id
      name
      address
      city
      state
      country
    }
    dateTime
    createdTime
    endTime
    going {
      totalCount
    }
    isAttending
    isOnline
    eventType
    status
    series {
      __typename
      description
      weeklyRecurrence {
        weeklyDaysOfWeek
        weeklyInterval
      }
      monthlyRecurrence {
        monthlyDayOfWeek
        monthlyWeekOfMonth
      }
    }
    featuredEventPhoto {
      id
      baseUrl
      highResUrl
    }
    displayPhoto {
      id
      baseUrl
      highResUrl
    }
    rsvpState
    rsvps(first: 5) {
      totalCount
      edges {
        node {
          id
          member {
            id
            name
            memberPhoto {
              id
              source: highResUrl
            }
          }
        }
      }
    }
    maxTickets
    actions
    rsvpSettings {
      rsvpsClosed
    }
    isNetworkEvent
    networkEvent {
      rsvpCount
      groupCount
    }
    socialLabels
    socialProofInsights {
      ...SocialProofInsightsForGroupHome
    }
  }

fragment SocialProofInsightsForGroupHome on SocialProofInsights {
    isTrendingEvent
    totalInterestedUsers
    interestedUsersSample {
      memberPhoto {
        id
        baseUrl
        highResUrl
      }
    }
  }
"""

GET_PAST_GROUP_EVENTS = """\
query getPastGroupEvents(
    $urlname: String!
    $after: String
    $afterDateTime: DateTime
    $beforeDateTime: DateTime
    $title: String
  ) {
    groupByUrlname(urlname: $urlname) {
      id
      organizer {
        id
        isStarterOrganizer
      }
      events(
        filter: {
          status: [ACTIVE, PAST, CANCELLED]
          afterDateTime: $afterDateTime
          beforeDateTime: $beforeDateTime
          title: $title
        }
        sort: DESC
        first: 10
        after: $after
      ) {
        totalCount
        pageInfo {
          endCursor
          hasNextPage
        }
        edges {
          node {
            ...CoreGroupHomeEvent
          }
        }
      }
    }
  }

fragment CoreGroupHomeEvent on Event {
    id
    title
    eventUrl
    description
    isSaved
    group {
      id
      name
      timezone
      keyGroupPhoto {
        id
        baseUrl
        highResUrl
      }
    }
    creatorMember {
      id
    }
    eventHosts {
      memberId
    }
    feeSettings {
      accepts
      currency
      amount
    }
    venue {
      id
      name
      address
      city
      state
      country
    }
    dateTime
    createdTime
    endTime
    going {
      totalCount
    }
    isAttending
    isOnline
    eventType
    status
    series {
      __typename
      description
      weeklyRecurrence {
        weeklyDaysOfWeek
        weeklyInterval
      }
      monthlyRecurrence {
        monthlyDayOfWeek
        monthlyWeekOfMonth
      }
    }
    featuredEventPhoto {
      id
      baseUrl
      highResUrl
    }
    displayPhoto {
      id
      baseUrl
      highResUrl
    }
    rsvpState
    rsvps(first: 5) {
      totalCount
      edges {
        node {
          id
          member {
            id
            name
            memberPhoto {
              id
              source: highResUrl
            }
          }
        }
      }
    }
    maxTickets
    actions
    rsvpSettings {
      rsvpsClosed
    }
    isNetworkEvent
    networkEvent {
      rsvpCount
      groupCount
    }
    socialLabels
    socialProofInsights {
      ...SocialProofInsightsForGroupHome
    }
  }

fragment SocialProofInsightsForGroupHome on SocialProofInsights {
    isTrendingEvent
    totalInterestedUsers
    interestedUsersSample {
      memberPhoto {
        id
        baseUrl
        highResUrl
      }
    }
  }
"""

GET_EVENT_HOME_CLIENT_ONLY = """\
query getEventHomeClientOnly($eventId: ID!) {
    event(id: $eventId) {
      ...EventHomeClientOnly
    }
  }

fragment EventHomeClientOnly on Event {
    id
    attendanceForecast {
      lowerBound
      expected
      upperBound
      rsvpCount
      confidenceLevel
      dataQuality
      historicalEventCount
      historicalRsvpCount
      modelVersion
    }
    isSaved
    isAttending
    going {
      totalCount
    }
    token
    venues {
      id
      eventVenueOptions {
        rsvpLimit
        guestLimit
        goingCount
        howToFindUs
        feeSettings {
          amount
          accepts
          currency
        }
      }
      earlyBirdDiscount {
        id
        amount
        daysBefore
        maximumQuantity
        discountTicketsRemaining
        promotionEnds
      }
    }
    feeSettings {
      earlyBirdDiscount {
        promotionEnds
      }
    }
    rsvpSurveySettings {
      requiresProQuestionnaire
      questions {
        questionId
        text
        type
        required
        characterLimit
        id
        questionType
        options
      }
    }
    newRsvpSurveySettings: rsvpSurveySettings(newSurvey: true) {
      requiresProQuestionnaire
      questions {
        ...Question
      }
    }
    rsvpQuestions {
      questionId
      text
    }
    rsvp {
      id
      guestsCount
      isHost
      payStatus
      venue {
        venueType
      }
    }
    howToFindUs
    actions
    isEventCommentsEnabled
    isCheckInEnabled
    eventChat {
      id
      activeConvoMembers {
        member {
          id
        }
        eventRole
      }
      messages(first: 20) {
        totalCount
        edges {
          node {
            id
            text
            reactions {
              emoji
              count
              reactedByMe
            }
            created
            updated
            member {
              id
              name
              memberPhoto {
                id
                baseUrl
              }
            }
          }
        }
      }
    }
    eventChatWelcomeMessage
    rsvpState
    fundraising {
      enabled
    }
    networkEvent {
      rsvpCount
      groupCount
    }
    creatorMember {
      id
      memberPhoto {
        id
        baseUrl
      }
      name
    }
    group {
      id
      isPrimaryOrganizer
      isMember
      lat
      lon
      membershipMetadata {
        status
        role
      }
      memberPhoto {
        id
        baseUrl
      }
      fundraising {
        enabled
        fundraiser {
          id
        }
      }
      stats {
        eventRatings {
          total
          average
        }
      }
      organizer {
        id
        paypalSettings {
          eventFee {
            enabled
            paypalMerchantAccount {
              id
              status
            }
          }
        }
        isStarterOrganizer
      }
      membershipMetadata {
        role
        status
      }
      proNetwork {
        id
        urlname
        name
        link
        isMemberEmailShared: isProEmailShared
      }
      isMember
    }
    socialLabels
    rsvpState
    rsvp {
      id
      answer {
        text
      }
    }
  }

fragment Question on RsvpSurveySettingsQuestion {
    id
    questionType
    text
    required
    options
    questionRequired
  }
"""

GET_EVENT_BY_ID_FOR_ATTENDEES = """\
query getEventByIdForAttendees(
    $eventId: ID!
    $first: Int
    $after: String
    $filter: RsvpFilter
    $sort: RsvpSort
  ) {
    event(id: $eventId) {
      ...EventByIdForAttendees
    }
  }

fragment EventByIdForAttendees on Event {
    id
    attendanceForecast {
      lowerBound
      expected
      upperBound
      rsvpCount
      confidenceLevel
      dataQuality
      historicalEventCount
      historicalRsvpCount
      modelVersion
    }
    title
    eventUrl
    dateTime
    endTime
    status
    eventType
    eventHosts {
      memberId
    }
    rsvpQuestions {
      text
    }
    actions
    guestLimit
    maxTickets
    rsvpSettings {
      rsvpCloseTime
      rsvpOpenTime
    }
    venue {
      name
      address
    }
    venues {
      id
      venueType
      eventVenueOptions {
        goingCount
        rsvpLimit
        guestLimit
      }
    }
    canSeeAttendees
    isCheckInEnabled
    rsvps(first: $first, after: $after, filter: $filter, sort: $sort) {
      totalCount
      yesCount
      noCount
      waitlistCount
      attendedCount
      noShowCount
      absentCount
      edges {
        node {
          ...AttendeesRsvp
        }
      }
      pageInfo {
        hasPreviousPage
        hasNextPage
        endCursor
      }
    }
    group {
      id
      isPrivate
      isMember
      isPrimaryOrganizer
      membershipMetadata {
        role
      }
      link
      urlname
      starterTierMaxRsvpLimit
      organizer {
        id
        isStarterOrganizer
      }
    }
  }

fragment AttendeesRsvp on Rsvp {
    id
    member {
      id
      name
      gender
      allowableActions
      memberPhoto {
        id
        baseUrl
      }
      profilePrivacy {
        showInterests
        whoCanContact
      }
      topics {
        edges {
          node {
            id
            name
          }
        }
      }
      commonTopics {
        totalCount
        edges {
          node {
            id
            name
          }
        }
      }
      reasonsForJoining
      isFamiliarFace
      hasWaitlistPriority
      noShowCount
      eventsAttended
      isSuperOrganizer
    }
    membership {
      role
      status
      title
    }
    updated
    isHost
    isFirstEvent
    status
    payStatus
    guestsCount
    answer {
      text
    }
    actions
    event {
      id
      guestsAllowed
      guestLimit
      numberOfAllowedGuests
      isAttending
      maxTickets
      group {
        id
        link
      }
      feeSettings {
        amount
      }
    }
    venue {
      id
      venueType
    }
    isRsvpUnlocked
  }
"""

GROUP_SIMILAR_EVENTS_BY_EVENT = """\
query groupSimilarEventsByEvent($eventId: ID!, $dataConfiguration: String, $takeEvents: Int = 3) {
    similarEvents(first: $takeEvents, eventId: $eventId, dataConfiguration: $dataConfiguration) {
      edges {
        node {
          ...GroupHomeEvent
        }
      }
    }
  }

fragment GroupHomeEvent on Event {
    id
    title
    status
    isSaved
    featuredEventPhoto {
      source: highResUrl
      baseUrl
      highResUrl
      id
    }
    displayPhoto {
      source: highResUrl
      baseUrl
      highResUrl
      id
    }
    description
    isOnline
    eventType
    venue {
      id
      name
      address
      city
      state
      country
    }
    isAttending
    eventUrl
    going {
      totalCount
    }
    dateTime
    endTime
    isFeatured
    group {
      id
      name
      timezone
    }
    actions
    isNetworkEvent
    rsvpState
    rsvps {
      edges {
        node {
          id
          member {
            id
            name
            memberPhoto {
              id
              source: highResUrl
            }
          }
        }
      }
    }
    feeSettings {
      currency
      amount
    }
    rsvpSettings {
      rsvpsClosed
    }
    socialLabels
  }
"""

GET_ALL_TOPIC_GROUPS_BY_URLKEY = """\
query getAllTopicGroupsByUrlkey($first: Int!, $urlkey: String!, $after: String) {
    topicByUrlkey(urlkey: $urlkey) {
      id
      groups(first: $first, after: $after) {
        totalCount
        edges {
          node {
            urlname
            name
            city
            country
            state
          }
        }
        pageInfo {
          hasPreviousPage
          hasNextPage
          endCursor
        }
      }
    }
  }
"""

GET_SUGGESTED_TOPICS = """\
query getSuggestedTopics($query: String!) {
    suggestTopics(query: $query, first: 5, excludeMemberTopics: true) {
      edges {
        node {
          id
          urlkey
          name
        }
      }
    }
  }
"""

GET_LOCATION_SEARCH = """\
query getLocationSearch(
    $query: String
    $lat: Float
    $lon: Float
    $dataConfiguration: String
    $variant: String
    $useImprovedGeoHashIndex: Boolean
    $sortByMaxDensity: Boolean
    $offset: Int
  ) {
    result: locationSearch(
      query: $query
      lat: $lat
      lon: $lon
      dataConfiguration: $dataConfiguration
      variant: $variant
      useImprovedGeoHashIndex: $useImprovedGeoHashIndex
      sortByMaxDensity: $sortByMaxDensity
      offset: $offset
    ) {
      city
      country
      lat
      lon
      name
      state
      timeZone
      borough
      localizedCountryName
      neighborhood
      zip
    }
  }
"""

# A topic's worldwide counts. The topic page itself reads
# countryStats(countryCode: "global"), which answers 0 for most topics
# (hiking: 0 there, 1,937 groups and 4.4M members here; 2026-11-23).
GET_TOPIC_STATS = """\
query getTopicStats($urlkey: String!) {
    topicByUrlkey(urlkey: $urlkey) {
      id
      stats {
        groupCount
        memberCount
      }
    }
  }
"""

# operation name -> (the id the page sends, or None for one no page sends; the operation's text)
OPERATIONS = {
    "eventSearchWithSeries": ("e23460c42028dfbc0d9c24b97fb52378b9e022899d94011f737b65d13bb9a0d2",
        EVENT_SEARCH_WITH_SERIES),
    "recommendedEventsWithSeries": ("fe189ee9858cbae80c3cb4100ed216f1c60b4f2956d26e27187fb6d0aca23506",
        RECOMMENDED_EVENTS_WITH_SERIES),
    "groupSearch": ("45d140d914d3b2d532ecf7c2e4bad73d03b490c9a01d369192cdd219146ddcf3",
        GROUP_SEARCH),
    "getRecommendedGroups": ("a3b1823dd39f77e05b1c7066387cd899d251a55ab174e5f09fda72c927d812f7",
        GET_RECOMMENDED_GROUPS),
    "groupHome": ("012d7194e1b3746c687a04e05cdf39a25e33a7f8228bb3c563ee55432c718bee",
        GROUP_HOME),
    "getGroupFeedbackInfo": ("ddc5bfb38fcec6927425fdebf0b64c4be00eccf8c39a1356867048323fcd7bce",
        GET_GROUP_FEEDBACK_INFO),
    "getUpcomingGroupEvents": ("81a7529c2bcfd8739837a20305ed04bc9555a1c2629663c62f79df5e5bad70ab",
        GET_UPCOMING_GROUP_EVENTS),
    "getPastGroupEvents": ("7ee35e6c00aafa75572fea738e4a6d7188354af9c3836ed5bd4c25d22c95d271",
        GET_PAST_GROUP_EVENTS),
    "getEventHomeClientOnly": ("0f4b43ffe8c6ad6fff9faee2cc66eeeacfe5ad96d7e14711b7de86088dac1401",
        GET_EVENT_HOME_CLIENT_ONLY),
    "getEventByIdForAttendees": ("cafa900bbe462e226752f9f51525de33535ca2de2acaac912b7763c86484aba8",
        GET_EVENT_BY_ID_FOR_ATTENDEES),
    "groupSimilarEventsByEvent": ("36b0a51e81fd233c1385b23b7a86a6b531e85ece6ec446c57405a89068aa3350",
        GROUP_SIMILAR_EVENTS_BY_EVENT),
    "getAllTopicGroupsByUrlkey": ("57404a125c914f99c402d3f0fa227ede59695da575d1e95e313e6c90b540f747",
        GET_ALL_TOPIC_GROUPS_BY_URLKEY),
    "getSuggestedTopics": ("a8331735d72cc4d85fdcf82266135dfbffc9496d0c611eb6157a8abe0e8674fc",
        GET_SUGGESTED_TOPICS),
    "getLocationSearch": ("950b939f7033b26849b13e829e04cad7fb6b6e4593e97499fceb3ff21764206d",
        GET_LOCATION_SEARCH),
    "getTopicStats": (None, GET_TOPIC_STATS),
}

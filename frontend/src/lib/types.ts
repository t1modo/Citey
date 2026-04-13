interface LinkedAuthorEntry {
  id: string;
  name: string | null;
}

export interface UserProfile {
  uid: string;
  email: string;
  display_name: string | null;
  notification_email: string | null;
  notify_enabled: boolean;
  notify_new_publications: boolean;
  scholar_url: string | null;
  linked_author_id: string | null;
  linked_author_name: string | null;
  additional_linked_authors: LinkedAuthorEntry[];
  name_aliases: string[];
  created_at: string;
  updated_at: string;
}

export interface TrackedWork {
  id: string;
  doi: string;
  title: string | null;
  authors: string[];
  year: number | null;
  venue: string | null;
  work_type: string | null;
  topics: string[];
  last_checked_at: string | null;
  added_at: string | null;
  citation_count: number;
  new_citations_30d: number;
  s2_citation_count: number | null;
  openalex_citation_count: number | null;
}

export interface Notification {
  id: string;
  cited_work_id: string;
  cited_work_title: string;
  citing_work_id: string;
  citing_work_title: string;
  citing_work_doi: string | null;
  citing_work_url: string | null;
  citing_authors: string[];
  citing_affiliations: string[];
  citing_year: number | null;
  citing_publication_date: string | null;
  seen: boolean;
  created_at: string | null;
}

export interface UpdateProfileData {
  display_name?: string | null;
  notification_email?: string | null;
  notify_enabled?: boolean;
  notify_new_publications?: boolean;
  scholar_url?: string | null;
  name_aliases?: string[];
}

export interface PaginatedNotifications {
  items: Notification[];
  total: number;
  unseen: number;
  page: number;
  limit: number;
  pages: number;
}

export interface AuthorAffiliation {
  name: string;
  year_range: string | null;
}

export interface AuthorCandidate {
  id: string;
  display_name: string;
  works_count: number;
  h_index: number;
  affiliations: AuthorAffiliation[];
  topics: string[];
  source: "openalex" | "semantic_scholar" | "inspire" | "dblp";
}

export interface PaperAuthorsResult {
  paper_title: string;
  paper_year: number | null;
  authors: AuthorCandidate[];
}

export type AddWorkResult =
  | { status: "added"; work: TrackedWork }
  | {
      status: "author_not_found";
      linkedAuthor: string;
      paperTitle: string;
      paperAuthors: string[];
    };

import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../api-config';
import { DocumentDetail, DocumentListItem } from '../models/document.model';

@Injectable({ providedIn: 'root' })
export class DocumentService {
  private readonly http = inject(HttpClient);

  list(): Observable<DocumentListItem[]> {
    return this.http.get<DocumentListItem[]>(`${API_BASE_URL}/documents`);
  }

  get(id: number): Observable<DocumentDetail> {
    return this.http.get<DocumentDetail>(`${API_BASE_URL}/documents/${id}`);
  }

  upload(file: File): Observable<DocumentDetail> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<DocumentDetail>(`${API_BASE_URL}/documents/upload`, formData);
  }
}

import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { DocumentService } from '../../core/services/document.service';

const ALLOWED_EXTENSIONS = ['.txt', '.pdf', '.docx'];

@Component({
  selector: 'app-upload',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './upload.component.html',
  styleUrl: './upload.component.css',
})
export class UploadComponent {
  private readonly documentService = inject(DocumentService);
  private readonly router = inject(Router);

  readonly selectedFile = signal<File | null>(null);
  readonly isDragging = signal(false);
  readonly uploading = signal(false);
  readonly errorMessage = signal<string | null>(null);

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.isDragging.set(true);
  }

  onDragLeave(): void {
    this.isDragging.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragging.set(false);
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      this.handleFile(file);
    }
  }

  onFileSelected(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (file) {
      this.handleFile(file);
    }
  }

  private handleFile(file: File): void {
    const extension = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      this.errorMessage.set(`Unsupported file type. Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`);
      return;
    }
    this.errorMessage.set(null);
    this.selectedFile.set(file);
  }

  submit(): void {
    const file = this.selectedFile();
    if (!file) {
      return;
    }

    this.uploading.set(true);
    this.errorMessage.set(null);

    this.documentService.upload(file).subscribe({
      next: (document) => this.router.navigate(['/documents', document.id]),
      error: (err) => {
        this.uploading.set(false);
        this.errorMessage.set(err?.error?.detail ?? 'Upload failed. Please try again.');
      },
    });
  }
}

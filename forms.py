"""نماذج لوحة الإدارة مع تحقق خادمي من المدخلات."""

from flask_wtf import FlaskForm
from wtforms import (
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import URL, DataRequired, Length, NumberRange, Optional


class LoginForm(FlaskForm):
    """نموذج دخول المشرف."""

    username = StringField("اسم المستخدم", validators=[DataRequired(), Length(max=80)])
    password = PasswordField("كلمة المرور", validators=[DataRequired(), Length(max=256)])
    submit = SubmitField("تسجيل الدخول")


class DiseaseForm(FlaskForm):
    """نموذج إنشاء أو تعديل مرض تعليمي."""

    name_ar = StringField("الاسم بالعربية", validators=[DataRequired(), Length(max=200)])
    name_en = StringField("الاسم بالإنجليزية", validators=[DataRequired(), Length(max=200)])
    system = StringField("الجهاز أو التخصص", validators=[DataRequired(), Length(max=120)])
    definition = TextAreaField("التعريف", validators=[DataRequired(), Length(max=5000)])
    etiology = TextAreaField("الأسباب", validators=[DataRequired(), Length(max=5000)])
    symptoms = TextAreaField("الأعراض", validators=[DataRequired(), Length(max=5000)])
    diagnosis = TextAreaField("التشخيص", validators=[DataRequired(), Length(max=5000)])
    treatment = TextAreaField("العلاج", validators=[DataRequired(), Length(max=7000)])
    importance = IntegerField("الأهمية من 1 إلى 3", validators=[DataRequired(), NumberRange(min=1, max=3)])
    week_number = IntegerField("رقم الأسبوع", validators=[DataRequired(), NumberRange(min=1, max=53)])
    image_url = StringField("رابط الصورة (اختياري)", validators=[Optional(), URL(), Length(max=1000)])
    submit = SubmitField("حفظ")

    def to_payload(self) -> dict:
        """إرجاع الحقول المسموح بإرسالها إلى قاعدة البيانات فقط."""
        return {
            "name_ar": self.name_ar.data.strip(),
            "name_en": self.name_en.data.strip(),
            "system": self.system.data.strip(),
            "definition": self.definition.data.strip(),
            "etiology": self.etiology.data.strip(),
            "symptoms": self.symptoms.data.strip(),
            "diagnosis": self.diagnosis.data.strip(),
            "treatment": self.treatment.data.strip(),
            "importance": self.importance.data,
            "week_number": self.week_number.data,
            "image_url": self.image_url.data.strip() if self.image_url.data else None,
        }


class QuestionForm(FlaskForm):
    """نموذج إنشاء أو تعديل سؤال اختيار من متعدد."""

    disease_id = SelectField("المرض", validators=[DataRequired()], choices=[])
    question = TextAreaField("السؤال", validators=[DataRequired(), Length(max=2000)])
    option_a = StringField("الخيار A", validators=[DataRequired(), Length(max=1000)])
    option_b = StringField("الخيار B", validators=[DataRequired(), Length(max=1000)])
    option_c = StringField("الخيار C", validators=[DataRequired(), Length(max=1000)])
    option_d = StringField("الخيار D", validators=[DataRequired(), Length(max=1000)])
    correct_answer = SelectField(
        "الإجابة الصحيحة",
        validators=[DataRequired()],
        choices=[("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")],
    )
    explanation = TextAreaField("الشرح", validators=[DataRequired(), Length(max=3000)])
    difficulty = IntegerField("الصعوبة من 1 إلى 5", validators=[DataRequired(), NumberRange(min=1, max=5)])
    submit = SubmitField("حفظ")

    def to_payload(self) -> dict:
        """إرجاع قائمة بيضاء بالحقول المقبولة."""
        return {
            "disease_id": self.disease_id.data,
            "question": self.question.data.strip(),
            "option_a": self.option_a.data.strip(),
            "option_b": self.option_b.data.strip(),
            "option_c": self.option_c.data.strip(),
            "option_d": self.option_d.data.strip(),
            "correct_answer": self.correct_answer.data,
            "explanation": self.explanation.data.strip(),
            "difficulty": self.difficulty.data,
        }


class DeleteForm(FlaskForm):
    """نموذج مستقل لضمان وجود CSRF في عمليات الحذف."""

    submit = SubmitField("حذف")

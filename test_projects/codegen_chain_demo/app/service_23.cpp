#include "service_23.h"

Service23::Service23() {}

void Service23::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service23::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
